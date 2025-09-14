# src/transformers.py
from __future__ import annotations
import argparse
import datetime
import json
import os
from typing import Any, Dict, List, Optional, Union
from collections import defaultdict

import pandas as pd
from dateutil import parser as dtparser

from validators import Course, read_json
# NEW: allow in-app scraping for UX
try:
    from scraper import ColumbiaDOCScraper
except Exception:
    ColumbiaDOCScraper = None  # still ok if you only use pre-scraped files

DAY_ORDER = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]

# ----------------- time & credits helpers -----------------

def parse_time_to_24h(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    if not s or s.upper() in {"TBA", "ARR", "ARRANGED"}:
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

def normalize_credits(raw: Union[str, int, float, None]) -> Union[int, float, str, None]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return raw
    s = str(raw).strip()
    try:
        return float(s) if "." in s else int(s)
    except Exception:
        return s

def hhmm_to_minutes(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)

# ----------------- Course -> rows, with recitation awareness -----------------

def _collect_recitations(courses: List[Course]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build a map of course_code -> list of recitation meeting dicts.
    Uses explicit Section.component when present; otherwise falls back to:
      zero-credit OR title containing 'recit'.
    """
    rec_by_course: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in courses:
        cr = normalize_credits(c.credits)
        title_up = (c.title or "").upper()
        for sec in c.sections:
            comp = getattr(sec, "component", None)
            is_recit = False
            if comp and comp.lower().startswith("recit"):
                is_recit = True
            elif (isinstance(cr, (int, float)) and float(cr) == 0.0) or ("RECIT" in title_up):
                is_recit = True
            if is_recit:
                for m in sec.meetings:
                    rec_by_course[c.course_code].append({
                        "days": m.days,
                        "start_time": m.start_time,
                        "end_time": m.end_time,
                        "location": " ".join(filter(None, [
                            (m.location.building if m.location else None),
                            (m.location.room if m.location else None)
                        ])) if m.location else None,
                        "section": sec.section,
                        "instructor": sec.instructor,
                    })
    return rec_by_course

def _summarize_recitations(options: List[Dict[str, Any]], limit: int = 3) -> str:
    """Create a short human-readable summary like 'F 10:10–11:00; Th 19:10–20:00 …'"""
    parts = []
    for i, o in enumerate(options):
        if i >= limit:
            parts.append("…")
            break
        days = "".join(o.get("days") or [])
        st, et = o.get("start_time"), o.get("end_time")
        times = f"{st}–{et}" if st and et else (st or et or "TBA")
        loc = o.get("location")
        parts.append(f"{days} {times}" + (f" ({loc})" if loc else ""))
    return "; ".join(parts)

def to_rows(courses: List[Course]) -> List[Dict[str, Any]]:
    """
    Flatten Course objects into meeting-level rows that Streamlit can display & filter,
    and enrich rows with recitation metadata for the *same course*.
    """
    rows: List[Dict[str, Any]] = []
    rec_by_course = _collect_recitations(courses)

    for c in courses:
        cr = normalize_credits(c.credits)
        for sec in c.sections:
            comp = getattr(sec, "component", None)
            # Handle sections without explicit meeting blocks (rare but possible)
            if not sec.meetings:
                rows.append({
                    "university": c.university,
                    "subject": c.subject,
                    "course_code": c.course_code,
                    "title": c.title,
                    "credits": cr,
                    "term": sec.term,
                    "section": sec.section,
                    "crn": sec.crn,
                    "instructor": sec.instructor,
                    "component": comp,
                    "days": [],
                    "start_time": None,
                    "end_time": None,
                    "start_minutes": None,
                    "end_minutes": None,
                    "location": None,
                    "has_recitation": len(rec_by_course.get(c.course_code, [])) > 0,
                    "recitation_options": rec_by_course.get(c.course_code, []),
                    "recitation_summary": _summarize_recitations(rec_by_course.get(c.course_code, [])),
                    "short_desc": (c.description or "")[:140].strip(),
                })
                continue

            for m in sec.meetings:
                st, et = m.start_time, m.end_time
                rows.append({
                    "university": c.university,
                    "subject": c.subject,
                    "course_code": c.course_code,
                    "title": c.title,
                    "credits": cr,
                    "term": sec.term,
                    "section": sec.section,
                    "crn": sec.crn,
                    "instructor": sec.instructor,
                    "component": comp,
                    "days": m.days,
                    "start_time": st,
                    "end_time": et,
                    "start_minutes": hhmm_to_minutes(st) if st else None,
                    "end_minutes": hhmm_to_minutes(et) if et else None,
                    "location": " ".join(filter(None, [
                        (m.location.building if m.location else None),
                        (m.location.room if m.location else None)
                    ])) if m.location else None,
                    "has_recitation": len(rec_by_course.get(c.course_code, [])) > 0,
                    "recitation_options": rec_by_course.get(c.course_code, []),
                    "recitation_summary": _summarize_recitations(rec_by_course.get(c.course_code, [])),
                    "short_desc": (c.description or "")[:140].strip(),
                })
    return rows

# ----------------- filtering & sorting -----------------

def filter_rows(rows: List[Dict[str, Any]],
                points: Optional[Union[int, float]] = None,
                day: Optional[str] = None,
                time_mode: str = "starts_at",          # "starts_at" or "overlaps"
                time_hhmm: Optional[str] = None,
                subject: Optional[str] = None,
                text_query: Optional[str] = None,
                hide_zero_credit: bool = False) -> List[Dict[str, Any]]:
    """
    Extended filter with subject, keyword, and 'hide 0 credit' options.
    """
    out = []
    tmin = None if not time_hhmm else (int(time_hhmm[:2]) * 60 + int(time_hhmm[3:]))
    q = (text_query or "").strip().lower()

    for r in rows:
        # Subject
        if subject and r.get("subject") != subject:
            continue

        # Zero-credit hiding
        if hide_zero_credit:
            try:
                if float(r.get("credits") or 0.0) == 0.0:
                    continue
            except Exception:
                pass

        # Points equality
        if points is not None:
            cr = r.get("credits")
            try:
                if float(cr) != float(points):
                    continue
            except Exception:
                continue

        # Day match
        if day:
            rdays = r.get("days") or []
            if day not in rdays:
                continue

        # Time constraint
        if tmin is not None:
            sm, em = r.get("start_minutes"), r.get("end_minutes")
            if sm is None or em is None:
                continue
            if time_mode == "starts_at":
                if sm != tmin:
                    continue
            else:  # overlaps
                if not (sm <= tmin <= em):
                    continue

        # Keyword search (title or instructor)
        if q:
            t = (r.get("title") or "").lower()
            instr = (r.get("instructor") or "").lower()
            if q not in t and q not in instr:
                continue

        out.append(r)

    # Sort by start time then course_code
    def sort_key(x):
        return (
            10**9 if x.get("start_minutes") is None else x["start_minutes"],
            x.get("course_code") or "",
        )

    return sorted(out, key=sort_key)

# ----------------- CLI driver (smoke / acceptance) -----------------

def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/sample_output.json")
    ap.add_argument("--points", type=float, default=None)
    ap.add_argument("--day", type=str, default=None)
    ap.add_argument("--time", type=str, default=None)
    ap.add_argument("--mode", type=str, default="starts_at", choices=["starts_at", "overlaps"])
    args = ap.parse_args()

    courses = read_json(args.input)
    rows = to_rows(courses)
    res = filter_rows(rows,
                      points=args.points,
                      day=args.day,
                      time_mode=args.mode,
                      time_hhmm=args.time)
    print(json.dumps(res[:5], indent=2))

# ----------------- Streamlit UI -----------------

if __name__ == "__main__":
    if os.getenv("ENV") == "TEST_FILTERS":
        # Acceptance test path (uses whatever is in data/sample_output.json)
        courses = read_json("data/sample_output.json")
        rows = to_rows(courses)
        out = filter_rows(rows, points=2, day="M", time_mode="starts_at", time_hhmm="16:30")
        assert all(float(r["credits"]) == 2.0 for r in out), "Not all results are 2 credits"
        assert all("M" in (r["days"] or []) for r in out), "Not all results are on Monday"
        out2 = filter_rows(rows, points=2, day="M", time_mode="overlaps", time_hhmm="16:30")
        assert len(out2) >= len(out), "Overlaps set should be >= starts_at set"
        print("ACCEPTANCE FILTERS: OK")
    else:
        import sys
        import streamlit as st

        st.set_page_config(page_title="Columbia Course Finder (POC)", layout="wide")
        # --- Light styling ---
        st.markdown("""
            <style>
              .big-title { font-size: 1.8rem; font-weight: 700; margin-bottom: .2rem; }
              .subtitle { color: #666; margin-bottom: 1rem; }
              .badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
                       background: #eef2ff; color: #334; font-size: 0.85rem; margin-right: 6px; }
            </style>
        """, unsafe_allow_html=True)
        st.markdown('<div class="big-title">Columbia Course Finder — Directory of Classes</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Filter by practical criteria and see recitations at a glance.</div>', unsafe_allow_html=True)

        # Resolve input path passed via "streamlit run src/transformers.py -- --input data/sample_output.json"
        input_path = "data/sample_output.json"
        if "--" in sys.argv:
            i = sys.argv.index("--")
            j = i + 1
            while j + 1 < len(sys.argv):
                if sys.argv[j] == "--input":
                    input_path = sys.argv[j + 1]
                    break
                j += 1

        # ------- Sidebar: Load data -------
        st.sidebar.header("Load data")
        data_source = st.sidebar.radio("Data source", options=["Existing file", "Scrape now"], index=0)

        if "courses_cache" not in st.session_state:
            st.session_state.courses_cache = None

        courses: List[Course]
        if data_source == "Existing file":
            input_path = st.sidebar.text_input("JSON file", value=input_path)
            if os.path.exists(input_path):
                courses = read_json(input_path)
                st.sidebar.success(f"Loaded {len(courses)} courses from file.")
            else:
                st.sidebar.error("File not found. Scrape or point to a valid JSON.")
                courses = []
        else:
            if ColumbiaDOCScraper is None:
                st.sidebar.error("Scraper module not available. Use the file mode or install dependencies.")
                courses = []
            else:
                term = st.sidebar.text_input("Term", value="Fall2025")
                scope = st.sidebar.radio("Scope", ["Seeded ALL subjects", "Choose subjects"], index=0)
                throttle = st.sidebar.slider("Throttle (sec/request)", min_value=0.0, max_value=2.0, value=0.7, step=0.1)
                enrich = st.sidebar.checkbox("Enrich descriptions & component", value=True)
                if scope == "Choose subjects":
                    subj_csv = st.sidebar.text_input("Subjects (comma-separated)", value="COMS,STAT")
                    subjects = [s.strip().upper() for s in subj_csv.split(",") if s.strip()]
                else:
                    subjects = ColumbiaDOCScraper.load_subjects_seed(None)

                if st.sidebar.button("Scrape now"):
                    scraper = ColumbiaDOCScraper(term_label=term, subjects=subjects, throttle=throttle, enrich_descriptions=enrich)
                    progress = st.sidebar.progress(0.0, text="Scraping...")
                    collected: List[Course] = []
                    for idx, s in enumerate(subjects, start=1):
                        try:
                            collected.extend(scraper.scrape_subject(s))
                        except Exception as e:
                            st.sidebar.warning(f"{s}: {e}")
                        progress.progress(idx / max(1, len(subjects)), text=f"Scraped {idx}/{len(subjects)} subjects")
                    st.session_state.courses_cache = collected
                    st.sidebar.success(f"Scraped {len(collected)} courses.")
                courses = st.session_state.courses_cache or []

        # Early exit if no courses
        if not courses:
            st.info("Load data from file or run a scrape to begin.")
            st.stop()

        # Flatten to rows (recitation-aware)
        rows = to_rows(courses)

        # ------- Sidebar: Filters -------
        st.sidebar.header("Filters")
        # Optional points filter (off by default to avoid zero results)
        pts_enabled = st.sidebar.checkbox("Filter by points (credits)?", value=False)
        pts_value = st.sidebar.number_input(
            "Points (credits)", min_value=0.0, max_value=10.0, value=2.0, step=0.5, disabled=not pts_enabled
        )
        pts = pts_value if pts_enabled else None

        # Subject list from data
        subjects_present = sorted({r.get("subject") for r in rows if r.get("subject")})
        subject = st.sidebar.selectbox("Subject", options=["(Any)"] + subjects_present, index=0)
        subject = None if subject == "(Any)" else subject

        # Day + Time
        day = st.sidebar.selectbox("Day", options=["(Any)", "M", "Tu", "W", "Th", "F", "Sa", "Su"], index=0)
        day = None if day == "(Any)" else day

        mode = st.sidebar.radio("Time mode", options=["starts_at", "overlaps"], index=0)
        time_enabled = st.sidebar.checkbox("Filter by time?", value=False)
        time_hhmm: Optional[str] = None
        if time_enabled:
            default_time = datetime.time(16, 30)
            time_label = st.sidebar.time_input("Time (24h)", value=default_time, step=300)
            time_hhmm = time_label.strftime("%H:%M")

        # Keyword & credit tweaks
        text_query = st.sidebar.text_input("Keyword (title or instructor)", value="")
        hide_zero = st.sidebar.checkbox("Hide 0‑credit components", value=True)

        # Compute filtered set
        filtered = filter_rows(
            rows, points=pts, day=day, time_mode=mode, time_hhmm=time_hhmm,
            subject=subject, text_query=text_query, hide_zero_credit=hide_zero
        )

        # ------- Topline metrics -------
        c1, c2, c3 = st.columns(3)
        c1.metric("Courses (loaded)", f"{len(courses):,}")
        c2.metric("Meetings (rows)", f"{len(rows):,}")
        c3.metric("Matches", f"{len(filtered):,}")

        # Diagnostics (collapsible)
        with st.expander("Diagnostics", expanded=False):
            st.write({
                "courses_count": len(courses),
                "rows_count": len(rows),
                "filtered_count": len(filtered),
                "using_points": pts if pts is not None else "(none)",
                "using_day": day if day else "(none)",
                "time_mode": mode,
                "time_hhmm": time_hhmm if time_hhmm else "(none)",
                "subject": subject or "(Any)"
            })
            if rows:
                st.text(f"Row keys sample: {list(rows[0].keys())}")

        st.caption(f"{len(filtered)} matching meeting(s). Sorted by start time.")

        show_recits = st.checkbox("Show recitation info", value=True)

        # Columns to display
        base_cols = [
            "course_code", "title", "credits", "term", "section", "crn",
            "instructor", "component", "days", "start_time", "end_time",
            "location", "short_desc"
        ]
        if show_recits:
            base_cols += ["has_recitation", "recitation_summary"]

        def _ensure_table(data: List[Dict[str, Any]], cols: List[str]) -> pd.DataFrame:
            df = pd.DataFrame(data)
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            return df[cols]

        table = _ensure_table(filtered, base_cols)

        if table.empty:
            st.warning(
                "No results for the current filters. "
                "Tips: turn off points, change day, switch time mode to 'overlaps', "
                "or pick a different time."
            )

        st.dataframe(table, use_container_width=True)

        # Download
        st.download_button(
            "Download results (JSON)",
            data=json.dumps(filtered, ensure_ascii=False, indent=2),
            file_name="results.json",
            mime="application/json",
        )
