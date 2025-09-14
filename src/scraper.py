# src/scraper.py
from __future__ import annotations
import argparse
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception
)

from validators import Course, Section, Meeting, Location, write_json

BASE = "https://doc.sis.columbia.edu"
UA = {"User-Agent": "ColumbiaCoursePOC/1.3 (+educational demo)"}

# Conservative seed (remove invalid/fragile codes like EEBM).
SUBJECTS_SEED = [
    # Engineering / CS
    "COMS", "CSEE", "ELEN", "BMEN", "MECE", "IEOR", "APMA",
    # Core STEM
    "MATH", "STAT", "PHYS", "CHEM", "BIOL",
    # Social science / humanities (sample)
    "ECON", "PSYC", "HIST", "PHIL", "ENGL", "SOCI", "HUMA"
]

# ------------------- HTTP utils -------------------

def polite_get(session: requests.Session, url: str, throttle: float = 1.0) -> requests.Response:
    time.sleep(max(throttle, 0.0))
    resp = session.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    return resp

def _retry_on_exception(exc: BaseException) -> bool:
    """
    Tell tenacity when to retry:
      - Retry on generic RequestException (timeouts, 5xx, etc.)
      - DO NOT retry on 404 (subject not found for term).
    """
    if isinstance(exc, requests.HTTPError) and getattr(exc, "response", None) is not None:
        if exc.response.status_code == 404:
            return False
    return isinstance(exc, requests.RequestException)

@retry(
    reraise=True,
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    retry=retry_if_exception(_retry_on_exception),
)
def fetch_text(session: requests.Session, url: str, throttle: float = 1.0) -> str:
    return polite_get(session, url, throttle).text

def robots_allows(session: requests.Session, host_base: str, path: str) -> bool:
    try:
        r = session.get(urljoin(host_base, "/robots.txt"), headers=UA, timeout=15)
        if r.status_code != 200:
            return True
        disallows = []
        ua_all = False
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent"):
                ua_all = "*" in line
            if ua_all and line.lower().startswith("disallow:"):
                disallows.append(line.split(":", 1)[1].strip())
        for rule in disallows:
            if not rule:
                return True
            if path.startswith(rule):
                return False
        return True
    except Exception:
        return True

# ------------------- Parsing helpers -------------------

def _to_24h(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    if not s or s.upper() in {"TBA", "ARR"}:
        return None
    s = s.replace("Noon", "12:00 PM").replace("noon", "12:00 PM")
    s = s.replace("Midnight", "12:00 AM").replace("midnight", "12:00 AM")
    try:
        t = dtparser.parse(s, fuzzy=True)
        return t.strftime("%H:%M")
    except Exception:
        if s.endswith("a") or s.endswith("p"):
            try:
                t = dtparser.parse(s + "m", fuzzy=True)
                return t.strftime("%H:%M")
            except Exception:
                return None
        return None

def _days_compact_to_tokens(s: str) -> List[str]:
    s = (s or "").strip().upper()
    if not s:
        return []
    mapping = {"M": "M", "T": "Tu", "W": "W", "R": "Th", "F": "F", "S": "Sa", "U": "Su"}
    out: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if ch == "T" and nxt == "H":
            out.append("Th")
            i += 2
            continue
        if ch == "T" and nxt == "U":
            out.append("Tu")
            i += 2
            continue
        out.append(mapping.get(ch, None) or "")
        i += 1
    seen = set()
    dedup = []
    for d in out:
        if d and d not in seen:
            seen.add(d)
            dedup.append(d)
    return dedup

# ------------------- Columbia DOC Scraper -------------------

class ColumbiaDOCScraper:
    """
    Scrapes Columbia Directory of Classes using static endpoints:
      - Subject HTML: /subj/{SUBJ}/_{TERM}.html           (for detail links)
      - Subject TEXT: /subj/{SUBJ}/_{TERM}_text.html      (for robust rows)
    """

    def __init__(self, term_label: str, subjects: Optional[List[str]] = None,
                 throttle: float = 1.0, enrich_descriptions: bool = True):
        self.term_label = self._normalize_term(term_label)  # "Fall2025"
        self.subjects = [s.strip().upper() for s in (subjects or []) if s.strip()]
        self.throttle = throttle
        self.enrich_descriptions = enrich_descriptions
        self.session = requests.Session()

    @staticmethod
    def _normalize_term(term_label: str) -> str:
        s = term_label.replace(" ", "")
        if not re.match(r"^(Fall|Spring|Summer)\d{4}$", s):
            raise ValueError(f"Bad term: {term_label}")
        return s

    @staticmethod
    def _term_human(term_label: str) -> str:
        return f"{term_label[:-4]} {term_label[-4:]}"

    def _subj_html_url(self, subject: str) -> str:
        return f"{BASE}/subj/{subject}/_{self.term_label}.html"

    def _subj_text_url(self, subject: str) -> str:
        return f"{BASE}/subj/{subject}/_{self.term_label}_text.html"

    def _map_section_links(self, html: str, subject: str) -> Dict[Tuple[str, str], str]:
        soup = BeautifulSoup(html, "lxml")
        mapping: Dict[Tuple[str, str], str] = {}
        anchors = soup.find_all("a")
        # e.g., /subj/MECE/E3100-20243-001/
        href_pat = re.compile(rf"/subj/{re.escape(subject)}/([A-Z]{{1,3}}\d{{3,4}})-(\d+)-([A-Za-z0-9]+)/")
        for a in anchors:
            href = a.get("href") or ""
            m = href_pat.search(href)
            if m:
                number, section = m.group(1), m.group(3)
                mapping[(number, section)] = urljoin(BASE, href)
        return mapping

    def _fetch_section_meta(self, url: str) -> Dict[str, Optional[str]]:
        """
        Returns {'description': str|None, 'component': str|None}
        Parses 'Course Description' and 'Type | Lecture/Recitation/Lab/...'
        """
        html = fetch_text(self.session, url, throttle=self.throttle)
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text("\n", strip=True)

        # Description
        desc = None
        m = re.search(r"Course Description\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            desc = m.group(1).strip()
            desc = re.split(
                r"(Web Site|Department|Enrollment|Subject|Number|Section|Division|Method of Instruction|Type)\s*\|",
                desc, maxsplit=1
            )[0]
            desc = re.sub(r"\s+", " ", desc).strip()
            if desc:
                desc = desc[:1000]

        # Component Type
        comp = None
        m2 = re.search(r"Type\s*\|\s*([A-Za-z /-]+)", text, flags=re.IGNORECASE)
        if m2:
            comp = m2.group(1).strip().title()

        return {"description": desc, "component": comp}

    def _parse_subject_text(self, text: str, subject: str) -> List[Dict[str, Any]]:
        """
        Parse the plain-text listing into records:
        Columns: Number Sec Call# Pts Title Day Time Room Building Faculty
        """
        rows: List[Dict[str, Any]] = []
        pat = re.compile(
            r"^\s*(?P<number>[A-Z]{1,3}\d{3,4})\s+"
            r"(?P<section>[A-Za-z0-9]{1,3})\s+"
            r"(?P<call>\d{3,6})\s+"
            r"(?P<pts>\d+(?:\.\d+)?)\s+"
            r"(?P<title>.+?)\s{2,}"
            r"(?P<days>[MTWRFSU]{1,7})\s+"
            r"(?P<start>\d{1,2}:\d{2}(?:\s*[ap]m?)?)"
            r"(?:\s*-\s*(?P<end>\d{1,2}:\d{2}(?:\s*[ap]m?)?))?"
            r"\s+(?P<room_building>.+?)\s{2,}"
            r"(?P<faculty>.+?)\s*$"
        )
        for line in text.splitlines():
            if not line or "Number Sec  Call#" in line:
                continue
            m = pat.match(line)
            if not m:
                continue
            gd = m.groupdict()
            rows.append({
                "subject": subject,
                "number": gd["number"],
                "section": gd["section"],
                "crn": gd["call"],
                "points": gd["pts"],
                "title": re.sub(r"\s+", " ", gd["title"]).strip(),
                "days_tokens": _days_compact_to_tokens(gd["days"]),
                "start_24": _to_24h(gd["start"]),
                "end_24": _to_24h(gd.get("end")),
                "room_building": re.sub(r"\s+", " ", gd["room_building"]).strip(),
                "instructor": re.sub(r"\s+", " ", gd["faculty"]).strip(),
            })
        return rows

    # -------------- Public entry --------------

    def scrape_subject(self, subject: str) -> List[Course]:
        """
        Scrape a single subject:
          * Fetch TEXT first (authoritative rows). If TEXT is 404 -> skip subject.
          * Try HTML (optional); if 404, just skip enrichment/link mapping.
        """
        # TEXT first
        try:
            text = fetch_text(self.session, self._subj_text_url(subject), throttle=self.throttle)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                print(f"[skip] {subject} {self.term_label}: 404 (no TEXT listing)")
                return []
            raise

        raw_rows = self._parse_subject_text(text, subject)

        # Try HTML for detail links (optional)
        link_map: Dict[Tuple[str, str], str] = {}
        try:
            html = fetch_text(self.session, self._subj_html_url(subject), throttle=self.throttle)
            link_map = self._map_section_links(html, subject)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                # No HTML index — proceed without enrichment.
                link_map = {}
            else:
                raise

        courses_by_key: Dict[Tuple[str, str], Course] = {}
        for r in raw_rows:
            key = (subject, r["number"])
            course = courses_by_key.get(key)
            if not course:
                course = Course(
                    university="Columbia University",
                    subject=subject,
                    number=r["number"],
                    course_code=f"{subject} {r['number']}",
                    title=r["title"],
                    credits=r["points"],
                    description=None,
                    prerequisites=None,
                    sections=[],
                )
                courses_by_key[key] = course

            # Location split
            building = room = None
            tokens = r["room_building"].split()
            if tokens and re.match(r"^\d+[A-Z]?$", tokens[0]):  # e.g., 417, 451, 301M
                room = tokens[0]
                building = " ".join(tokens[1:]) if len(tokens) > 1 else None
            else:
                building = r["room_building"]

            # Optional description + component enrichment (only if we have a link)
            desc, comp = None, None
            if self.enrich_descriptions and not course.description:
                detail_url = link_map.get((r["number"], r["section"]))
                if detail_url:
                    try:
                        meta = self._fetch_section_meta(detail_url)
                        desc = meta.get("description")
                        comp = meta.get("component")
                        if desc:
                            course.description = desc
                    except Exception:
                        pass

            # Fallback heuristic for component if not found
            if not comp:
                comp = ("Recitation" if (str(course.credits).strip() in {"0", "0.0"} or "RECIT" in course.title.upper())
                        else None)

            mtg = Meeting(
                days=r["days_tokens"],
                start_time=r["start_24"],
                end_time=r["end_24"],
                time_tba=False if (r["start_24"] or r["end_24"]) else True,
                location=Location(building=building, room=room),
            )
            sec = Section(
                term=self._term_human(self.term_label),
                crn=r["crn"],
                section=r["section"],
                instructor=r["instructor"],
                status=None,
                component=comp,
                meetings=[mtg],
            )
            course.sections.append(sec)

        return list(courses_by_key.values())

    def scrape(self) -> List[Course]:
        if not robots_allows(self.session, BASE, "/"):
            raise RuntimeError("robots.txt disallows scraping this path.")
        all_courses: List[Course] = []
        for subj in self.subjects:
            try:
                courses = self.scrape_subject(subj)
                all_courses.extend(courses)
            except requests.HTTPError as e:
                # Should be rare now; TEXT 404 is handled inside scrape_subject.
                code = e.response.status_code if e.response is not None else "?"
                print(f"[warn] {subj} {self.term_label}: HTTP {code}; continuing.")
                continue
            except Exception as e:
                print(f"[warn] {subj} {self.term_label}: {e}; continuing.")
                continue
        return all_courses

    # ------------ Subject discovery (seeded "ALL") ------------

    @staticmethod
    def load_subjects_seed(seed_path: Optional[str] = None) -> List[str]:
        # If a file is provided and exists, use it; else fall back to SUBJECTS_SEED.
        if seed_path and os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as f:
                items = [ln.strip().upper() for ln in f if ln.strip()]
            return items
        return SUBJECTS_SEED[:]

# ------------------- CLI -------------------

def main():
    ap = argparse.ArgumentParser(description="Scrape Columbia DOC by subject and term.")
    ap.add_argument("--term", required=True, help='e.g., "Fall2025" or "Fall 2025"')
    ap.add_argument("--subjects", help="Comma-separated subject codes, e.g., COMS,STAT,ECON")
    ap.add_argument("--all", action="store_true", help="Scrape all (seeded) subjects for this term")
    ap.add_argument("--subjects-file", default=None, help="Path to a file with one subject code per line")
    ap.add_argument("--out", default="data/sample_output.json")
    ap.add_argument("--throttle", type=float, default=1.0)
    ap.add_argument("--no-desc", action="store_true", help="Skip per-section description/component enrichment")
    args = ap.parse_args()

    if not args.all and not args.subjects:
        ap.error("Provide --subjects or use --all (optionally with --subjects-file).")

    if args.all:
        subjects = ColumbiaDOCScraper.load_subjects_seed(args.subjects_file)
    else:
        subjects = [s.strip() for s in args.subjects.split(",") if s.strip()]

    scraper = ColumbiaDOCScraper(
        term_label=args.term,
        subjects=subjects,
        throttle=args.throttle,
        enrich_descriptions=not args.no_desc
    )
    courses = scraper.scrape()
    write_json(args.out, courses)
    print(f"Wrote {len(courses)} courses across {len(subjects)} subjects to {args.out}")

if __name__ == "__main__":
    main()
