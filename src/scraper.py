# src/scraper.py
from __future__ import annotations

import argparse
import json
import os
import re
import string
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin


import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ---------------------------
# Constants & basic utilities
# ---------------------------

BASE = "https://doc.sis.columbia.edu"

TERM_SEMESTER_CODE = {"Spring": "1", "Summer": "2", "Fall": "3"}

HEADERS = {
    "User-Agent": "columbia-course-scraper/1.0 (+https://example.com; for demo/academic use)"
}

RECITATION_SEC_RE = re.compile(r"^\s*R\d+\s*$", re.I)
SECTION_DETAIL_PARENT_RE = re.compile(
    r"Required\s+(?:recitation|discussion|lab)\s+session\s+for\s+students\s+enrolled\s+in\s+([A-Z]{3,4})\s+([A-Z]?\d{4})",
    re.I,
)

DAY_MAP = {
    "M": "Mon",
    "T": "Tue",
    "W": "Wed",
    "R": "Thu",
    "F": "Fri",
    "S": "Sat",
    "U": "Sun",
}

# ---------------------------------
# Term normalization and conversions
# ---------------------------------

def normalize_term(term_str: str) -> str:
    t = term_str.strip().replace(" ", "")
    m = re.match(r"^(Spring|Summer|Fall)(\d{4})$", t)
    if not m:
        raise ValueError("Term must look like 'Fall2025' or 'Fall 2025'")
    return f"{m.group(1)}{m.group(2)}"

def term_to_sis_code(term_str: str) -> str:
    m = re.match(r"^(Spring|Summer|Fall)\s?(\d{4})$", term_str.strip())
    if not m:
        m = re.match(r"^(Spring|Summer|Fall)(\d{4})$", term_str.replace(" ", ""))
    semester, year = m.group(1), m.group(2)
    return f"{year}{TERM_SEMESTER_CODE[semester]}"

def term_human(term_str: str) -> str:
    # "Fall2025" -> "Fall 2025"
    t = normalize_term(term_str)
    return f"{t[:-4]} {t[-4:]}"

# -------------
# HTTP helpers
# -------------

def polite_sleep(throttle: float):
    if throttle and throttle > 0:
        time.sleep(throttle)

def polite_get(session: requests.Session, url: str, throttle: float = 0.4) -> requests.Response:
    polite_sleep(throttle)
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp

@retry(
    wait=wait_exponential(multiplier=0.8, min=0.5, max=8),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((requests.RequestException,))
)
def fetch_text(session: requests.Session, url: str, throttle: float = 0.4) -> str:
    return polite_get(session, url, throttle).text

# -----------------------
# Subject discovery (A–Z)
# -----------------------

def discover_subjects_for_term(term: str, session: requests.Session, throttle: float = 0.4) -> List[Dict[str, str]]:
    """
    Scrape the A..Z subject index pages and collect the valid subject codes for the given term.
    Returns: [{"code": "COMS", "name": "Computer Science"}, ...]
    """
    term_norm = normalize_term(term)  # "Fall2025"
    subjects: Dict[str, str] = {}

    for letter in string.ascii_uppercase:
        url = f"{BASE}/sel/subj-{letter}.html"  # e.g., https://doc.sis.columbia.edu/sel/subj-A.html
        html = fetch_text(session, url, throttle)
        soup = BeautifulSoup(html, "html.parser")

        # On each line: <Subject Name>  [Summer2025] [Fall2025] ...
        # We need anchors whose text equals term_norm; their hrefs point to /subj/<CODE>/_Fall2025.html
        for a in soup.find_all("a"):
            if (a.get_text(strip=True) or "") == term_norm:
                href = a.get("href") or ""
                m = re.search(r"/subj/([A-Z0-9_]+)/_", href)
                if not m:
                    continue
                code = m.group(1)
                # Subject name is in parent text ("Applied Mathematics Summer2025, Fall2025")
                parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
                # Strip trailing term tokens
                name = re.split(r"\b(Spring|Summer|Fall)\d{4}", parent_text)[0].strip(" ,:\u00A0")
                subjects[code] = name if name else code

    return [{"code": c, "name": subjects[c]} for c in sorted(subjects.keys())]

def save_subjects_file(path: str, term: str, subjects: List[Dict[str, str]]) -> None:
    payload = {
        "term": normalize_term(term),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "subjects": subjects,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def load_subject_codes_from_file(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        js = json.load(f)
    return [s["code"] for s in js.get("subjects", [])]

# -------------------------------------------
# Parsing the subject "plain text" list page
# -------------------------------------------

def _detect_columns(header_line: str) -> Dict[str, slice]:
    """
    Build fixed-width slices from the header row in the plain-text page.
    Header example (from DOC):
        Number Sec  Call#      Pts  Title                           Day Time          Room Building        Faculty
    """
    def col_pos(name: str) -> int:
        idx = header_line.find(name)
        if idx < 0:
            raise ValueError(f"Column '{name}' not found in header.")
        return idx

    # Get start indices
    starts = {
        "Number": col_pos("Number"),
        "Sec": col_pos("Sec"),
        "Call#": col_pos("Call#"),
        "Pts": col_pos("Pts"),
        "Title": col_pos("Title"),
        "Day": col_pos("Day"),
        "Time": col_pos("Time"),
        "Room": col_pos("Room"),
        "Building": col_pos("Building"),
        "Faculty": col_pos("Faculty"),
    }
    # Compute slices by next column start
    keys = ["Number", "Sec", "Call#", "Pts", "Title", "Day", "Time", "Room", "Building", "Faculty"]
    slices: Dict[str, slice] = {}
    for i, k in enumerate(keys):
        start = starts[k]
        end = len(header_line) if i == len(keys) - 1 else starts[keys[i + 1]]
        slices[k] = slice(start, end)
    return slices

def _parse_time_range(time_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Robust parser for Columbia DOC time strings.
    Accepts:
      - "1:10 pm-2:25 pm", "1:10pm - 2:25pm", "1:10 PM — 2:25 PM", "1:10 pm to 2:25 pm"
      - Numeric: "1410-1525", "900-1025"
      - Single time: "1:10 pm", "1410"  -> duplicate to both
      - "TBA" -> (None, None)

    Returns 24h labels ("HH:MM") or (None, None).
    """
    s_orig = (time_str or "").strip()
    if not s_orig:
        return (None, None)

    s = s_orig
    # Normalize unicode dashes, A.M./P.M., whitespace, "to"
    s = s.replace("\u00A0", " ")
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", s)  # all dash-like → "-"
    s = re.sub(r"\bto\b", "-", s, flags=re.I)
    s = re.sub(r"\.", "", s)  # a.m. -> am
    s = re.sub(r"\s+", " ", s).strip()

    if re.search(r"\bTBA\b", s, flags=re.I):
        return (None, None)

    def ampm_parts(tok: str) -> Tuple[int, int, Optional[str]]:
        m = re.search(r"^\s*(\d{1,2}):(\d{2})\s*([ap]m)?\s*$", tok, flags=re.I)
        if not m:
            return (-1, -1, None)
        hh, mm = int(m.group(1)), int(m.group(2))
        ap = (m.group(3) or "").lower() if m.group(3) else None
        return hh, mm, ap

    def to_24h(h: int, m: int, ap: Optional[str]) -> Optional[str]:
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        if ap:
            if ap == "pm" and h != 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
        return f"{h:02d}:{m:02d}"

    def hhmm_token(tok: str) -> Optional[str]:
        tok = tok.strip()
        m = re.match(r"^(\d{3,4})$", tok)
        if not m:
            return None
        val = m.group(1)
        if len(val) == 3:
            h = int(val[0])
            mm = int(val[1:])
        else:
            h = int(val[:2])
            mm = int(val[2:])
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return f"{h:02d}:{mm:02d}"
        return None

    # 1) AM/PM range (allow missing am/pm on one side; infer from the other)
    m = re.search(r"(\d{1,2}:\d{2}\s*(?:[ap]m)?)\s*-\s*(\d{1,2}:\d{2}\s*(?:[ap]m)?)", s, flags=re.I)
    if m:
        a_raw, b_raw = m.group(1), m.group(2)
        ah, am, aap = ampm_parts(a_raw)
        bh, bm, bap = ampm_parts(b_raw)
        if not aap and bap:
            aap = bap
        if not bap and aap:
            bap = aap
        a24 = to_24h(ah, am, aap)
        b24 = to_24h(bh, bm, bap)
        if a24 and b24:
            # If inferred same meridiem yields end <= start, flip end once
            ah24, am24 = map(int, a24.split(":"))
            bh24, bm24 = map(int, b24.split(":"))
            if (bh24 * 60 + bm24) <= (ah24 * 60 + am24) and (bap is None) and (aap in {"am", "pm"}):
                flip = "pm" if aap == "am" else "am"
                b24_alt = to_24h(bh, bm, flip)
                if b24_alt:
                    b24 = b24_alt
            return (a24, b24)

    # 2) HHMM numeric range
    m = re.search(r"\b(\d{3,4})\s*-\s*(\d{3,4})\b", s)
    if m:
        a = hhmm_token(m.group(1))
        b = hhmm_token(m.group(2))
        if a and b:
            ah, am = map(int, a.split(":"))
            bh, bm = map(int, b.split(":"))
            if (bh * 60 + bm) > (ah * 60 + am):
                return (a, b)

    # 3) Single AM/PM → duplicate
    m = re.search(r"\b(\d{1,2}:\d{2}\s*(?:[ap]m))\b", s, flags=re.I)
    if m:
        h, m_, ap = ampm_parts(m.group(1))
        t = to_24h(h, m_, ap)
        if t:
            return (t, t)

    # 4) Single HHMM → duplicate
    m = re.search(r"\b(\d{3,4})\b", s)
    if m:
        t = hhmm_token(m.group(1))
        if t:
            return (t, t)

    return (None, None)

def _credits_to_range(pts: str) -> Tuple[Optional[float], Optional[float]]:
    s = (pts or "").strip()
    if not s:
        return (None, None)
    if "-" in s:
        a, b = s.split("-", 1)
        try:
            return (float(a), float(b))
        except ValueError:
            return (None, None)
    try:
        v = float(s)
        return (v, v)
    except ValueError:
        return (None, None)

def _split_days(day_field: str) -> List[str]:
    s = (day_field or "").strip().upper()
    # Single letters with possible spaces; combine e.g. "TR" or "MW".
    s = re.sub(r"\s+", "", s)
    return [DAY_MAP[d] for d in s if d in DAY_MAP]

def parse_subject_text_page(text_html: str, subject_code: str, term_label: str) -> List[Dict]:
    """
    Given the _Fall2025_text.html content, parse into a list of section dicts.
    """
    # Extract the PRE-ish block (page is text wrapped in <pre> or monospaced <div>)
    soup = BeautifulSoup(text_html, "html.parser")
    raw = soup.get_text("\n", strip=False)

    lines = [ln.rstrip("\n") for ln in raw.splitlines()]
    # Find header line (has "Number Sec  Call#")
    header_idx = -1
    for i, ln in enumerate(lines):
        if "Number" in ln and "Call#" in ln and "Faculty" in ln:
            header_idx = i
            break
    if header_idx < 0:
        return []

    header = lines[header_idx]
    slices = _detect_columns(header)

    sections: List[Dict] = []

    i = header_idx + 1
    while i < len(lines):
        ln = lines[i]
        i += 1
        # Skip empty or "L Code" etc footers
        if not ln.strip():
            continue
        if re.search(r"\bL\s+Code\b", ln):
            break

        # Rows that contain a Number (course number) live in this line
        number = ln[slices["Number"]].strip()
        sec = ln[slices["Sec"]].strip()
        calln = ln[slices["Call#"]].strip()
        pts = ln[slices["Pts"]].strip()
        title = ln[slices["Title"]].strip()
        day = ln[slices["Day"]].strip()
        time_rng = ln[slices["Time"]].strip()
        room = ln[slices["Room"]].strip()
        building = ln[slices["Building"]].strip()
        faculty = ln[slices["Faculty"]].strip()

        # Some rows are continuation or notes lines (no Number/Sec), skip those here
        if not number and not sec and not title and not day and not time_rng and not faculty:
            continue

        # Normalize values
        start_time, end_time = _parse_time_range(time_rng)
        if start_time is None and end_time is None:
            # Fallback: if the Time slice was blank or misaligned, try the entire line
            st2, et2 = _parse_time_range(ln)
            if st2 and et2:
                start_time, end_time = st2, et2

        credits_min, credits_max = _credits_to_range(pts)

        # Peek next line for "Activity" (e.g., LECTURE/SEMINAR/LAB) if present
        component = None
        if i < len(lines):
            nxt = lines[i]
            if re.search(r"\bActivity\b", nxt) or re.search(r"\bLECTURE\b|\bSEMINAR\b|\bLAB\b|\bRECITATION\b", nxt, re.I):
                # Extract activity token if present
                m = re.search(r"\b(LECTURE|SEMINAR|LAB|RECITATION|INDEPEND|PRACTICUM|WORKSHOP|STUDIO)\b", nxt, re.I)
                if m:
                    component = m.group(1).upper()
                i += 1  # consume this extra line

        # Build the section record
        sections.append({
            "university": "Columbia University",
            "term": term_label,                       # e.g., "Fall 2025"
            "subject": subject_code,                  # e.g., "COMS"
            "number": number,                         # e.g., "W4701"
            "course_code": f"{subject_code} {number}",# e.g., "COMS W4701"
            "section": sec,                           # e.g., "001" or "R01"
            "crn": calln,                             # call number
            "title": title,
            "credits_min": credits_min,
            "credits_max": credits_max,
            "credits": credits_min if credits_min == credits_max else None,  # convenient single value if fixed
            "days": _split_days(day),
            "start_time": start_time,
            "end_time": end_time,
            "location": {
                "building": building or None,
                "room": room or None,
                "campus": None,
            },
            "instructor": faculty or None,
            "component": component,  # may be None; recitation detection also uses section code & credits
            "is_recitation": bool(RECITATION_SEC_RE.match(sec)) or (component == "RECITATION" and (credits_min == 0 or credits_min is None)),
            "parent_course_code": None,              # to be filled by linker if we can find it
            "detail_url": None,                      # to be filled later
            "short_desc": None,                      # optional enrichment
            "status": None,                          # optional enrichment
        })

    return sections

# -------------------------
# Detail page URL + linking
# -------------------------

def build_section_detail_url(subject: str, number: str, term_code: str, section: str) -> str:
    # e.g., /subj/APMA/E2001-20253-R01/
    return f"{BASE}/subj/{subject}/{number}-{term_code}-{section}/"

def try_link_recitation_parent(session: requests.Session, subj: str, number: str, sec: str, term_code: str, throttle: float = 0.35) -> Optional[str]:
    url = build_section_detail_url(subj, number, term_code, sec)
    try:
        html = fetch_text(session, url, throttle)
    except Exception:
        return None
    m = SECTION_DETAIL_PARENT_RE.search(html)
    if m:
        parent_subj, parent_num = m.group(1).upper(), m.group(2).upper()
        return f"{parent_subj} {parent_num}"
    return None

def link_recitations(sections: List[Dict], term_code: str, session: requests.Session) -> List[Dict]:
    """
    For sections flagged as recitations (R## or "RECITATION"/0 credits), try to find their parent lecture.
    Strategy:
      1) Strong: parse the section detail page (often states 'Required recitation session for ...').
      2) Fallback: find nearest lecture with matching subject + (normalized) title and credits>0.
    """
    def norm(s: Optional[str]) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    # Index candidate lectures by (subject, title_norm) -> set(course codes)
    lecture_index: Dict[Tuple[str, str], List[str]] = {}
    for s in sections:
        if not s.get("is_recitation"):
            # Consider "lecture-like" primary comps: credits>0 OR component indicates lecture/seminar
            if (s.get("credits_min") or 0) > 0 or (s.get("component") in ("LECTURE", "SEMINAR", "WORKSHOP", "STUDIO")):
                key = (s["subject"], norm(s["title"]))
                lecture_index.setdefault(key, [])
                cc = s["course_code"]
                if cc not in lecture_index[key]:
                    lecture_index[key].append(cc)

    for s in sections:
        if not s.get("is_recitation"):
            continue
        subj, number, sec = s["subject"], s["number"], s["section"]
        # Fill detail URL always; helpful for UI
        s["detail_url"] = build_section_detail_url(subj, number, term_code, sec)

        # Strong link via detail page
        parent = try_link_recitation_parent(session, subj, number, sec, term_code)
        if not parent:
            # Fallback: title match within the same subject
            key = (subj, norm(s["title"]))
            candidates = lecture_index.get(key, [])
            parent = candidates[0] if candidates else None
        if parent:
            s["parent_course_code"] = parent

    # Also attach detail_url for non-recitation sections (handy for "Open in DOC")
    for s in sections:
        if not s.get("detail_url"):
            s["detail_url"] = build_section_detail_url(s["subject"], s["number"], term_code, s["section"])

    return sections

# ----------------
# Top-level scrape
# ----------------

def scrape_subject(subject_code: str, term: str, session: requests.Session, throttle: float = 0.4) -> List[Dict]:
    """
    Scrape one subject for the given term using the plain-text page:
        https://doc.sis.columbia.edu/subj/<SUBJECT>/_<TERM>.html
        https://doc.sis.columbia.edu/subj/<SUBJECT>/_<TERM>_text.html
    """
    term_norm = normalize_term(term)   # Fall2025
    term_code = term_to_sis_code(term) # e.g., 20253
    term_label = term_human(term)      # e.g., "Fall 2025"

    # 1) Ensure the term-subject page exists (for status & "plain text version" link)
    subj_url = f"{BASE}/subj/{subject_code}/_{term_norm}.html"
    html = fetch_text(session, subj_url, throttle)

    # 2) Get the "plain text version"
    soup = BeautifulSoup(html, "html.parser")
    text_link = None
    for a in soup.find_all("a"):
        if "plain text version" in (a.get_text(strip=True) or "").lower():
            text_link = (a.get("href") or "").strip()
            break
    if not text_link:
        # Fallback: known shape (absolute-from-root path)
        text_link = f"/subj/{subject_code}/_{term_norm}_text.html"

    # Use urljoin to resolve any relative (e.g., "../subj/...") hrefs safely
    text_url = urljoin(f"{BASE}/", (text_link or "").strip())
    # Alternatively: urljoin(subj_url, text_link) also works; using BASE+'/' is fine too.

    text_html = fetch_text(session, text_url, throttle)

    # 3) Parse sections
    sections = parse_subject_text_page(text_html, subject_code, term_label)
    # 4) Link recitations → lectures; attach detail URLs
    sections = link_recitations(sections, term_code, session)
    return sections

def scrape_many(subject_codes: List[str], term: str, session: requests.Session, throttle: float = 0.4) -> List[Dict]:
    all_sections: List[Dict] = []
    for code in subject_codes:
        try:
            secs = scrape_subject(code, term, session, throttle)
            all_sections.extend(secs)
        except requests.HTTPError as e:
            # Non-offered subjects for the term often 404; skip gracefully
            if e.response is not None and e.response.status_code == 404:
                print(f"[warn] {code}: no listing for {term_human(term)}")
                continue
            raise
    return all_sections

def write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# -----------------------------
# CLI (useful for quick testing)
# -----------------------------

def main():
    parser = argparse.ArgumentParser(description="Columbia DOC scraper")
    parser.add_argument("--term", default="Fall 2025", help="e.g., 'Fall 2025' or 'Fall2025'")
    parser.add_argument("--discover-subjects", action="store_true", help="Discover all valid subjects for the term.")
    parser.add_argument("--save-subjects", default=None, help="Path to save discovered subjects JSON (e.g., data/subjects_Fall2025.json).")
    parser.add_argument("--subjects-file", default=None, help="Path to subjects JSON from discovery.")
    parser.add_argument("--subjects", nargs="*", default=None, help="Explicit subject codes to scrape (overrides subjects-file).")
    parser.add_argument("--scrape", action="store_true", help="After discovery, scrape subjects.")
    parser.add_argument("--max-subjects", type=int, default=None, help="Optional cap when scraping many subjects.")
    parser.add_argument("--out", default="data/sample_output.json", help="Where to write scraped JSON.")
    args = parser.parse_args()

    session = requests.Session()

    subjects_to_scrape: List[str] = []
    discovered = None

    if args.subjects:
        subjects_to_scrape = args.subjects
    elif args.subjects_file:
        subjects_to_scrape = load_subject_codes_from_file(args.subjects_file)
    else:
        # Auto-discover
        discovered = discover_subjects_for_term(args.term, session)
        if args.save_subjects:
            save_subjects_file(args.save_subjects, args.term, discovered)
            print(f"[info] wrote {len(discovered)} subjects to {args.save_subjects}")
        subjects_to_scrape = [s["code"] for s in discovered]

    if args.max_subjects:
        subjects_to_scrape = subjects_to_scrape[: args.max_subjects]

    if args.discover_subjects and not args.scrape:
        return 0

    if args.scrape:
        sections = scrape_many(subjects_to_scrape, args.term, session)
        write_json(args.out, sections)
        print(f"[ok] wrote {len(sections)} sections to {args.out}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
