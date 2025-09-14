# src/transformers.py
from __future__ import annotations
import argparse
import datetime
import json
import os
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from dateutil import parser as dtparser

from validators import Course, read_json

DAY_ORDER = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]


# ----------------- time & credits helpers -----------------

def parse_time_to_24h(s: Optional[str]) -> Optional[str]:
    """Best-effort parse to 'HH:MM' 24h."""
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
        # Handle '4:30p' / '10:10a' style suffixes
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


# ----------------- shaping: Course -> meeting rows -----------------

def to_rows(courses: List[Course]) -> List[Dict[str, Any]]:
    """
    Flatten Course objects into meeting-level rows that Streamlit can display & filter.
    Each row is one (course, section, meeting) tuple, with normalized times and days.
    """
    rows: List[Dict[str, Any]] = []
    for c in courses:
        for sec in c.sections:
            # Handle sections without explicit meeting blocks (rare but possible)
            if not sec.meetings:
                rows.append({
                    "university": c.university,
                    "course_code": c.course_code,
                    "title": c.title,
                    "credits": normalize_credits(c.credits),
                    "term": sec.term,
                    "section": sec.section,
                    "crn": sec.crn,
                    "instructor": sec.instructor,
                    "days": [],
                    "start_time": None,
                    "end_time": None,
                    "start_minutes": None,
                    "end_minutes": None,
                    "location": None,
                    "short_desc": (c.description or "")[:140].strip(),
                })
                continue

            for m in sec.meetings:
                st, et = m.start_time, m.end_time
                rows.append({
                    "university": c.university,
                    "course_code": c.course_code,
                    "title": c.title,
                    "credits": normalize_credits(c.credits),
                    "term": sec.term,
                    "section": sec.section,
                    "crn": sec.crn,
                    "instructor": sec.instructor,
                    "days": m.days,
                    "start_time": st,
                    "end_time": et,
                    "start_minutes": hhmm_to_minutes(st) if st else None,
                    "end_minutes": hhmm_to_minutes(et) if et else None,
                    "location": " ".join(filter(None, [
                        (m.location.building if m.location else None),
                        (m.location.room if m.location else None)
                    ])) if m.location else None,
                    "short_desc": (c.description or "")[:140].strip(),
                })
    return rows


# ----------------- filtering & sorting -----------------

def filter_rows(rows: List[Dict[str, Any]],
                points: Optional[Union[int, float]] = None,
                day: Optional[str] = None,
                time_mode: str = "starts_at",          # "starts_at" or "overlaps"
                time_hhmm: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Filter meeting rows by exact credit points, day membership, and time condition.
    - starts_at: start_minutes == query_minutes
    - overlaps:  start_minutes <= query_minutes <= end_minutes
    """
    out = []
    tmin = None if not time_hhmm else (int(time_hhmm[:2]) * 60 + int(time_hhmm[3:]))

    for r in rows:
        if points is not None:
            cr = r.get("credits")
            try:
                if float(cr) != float(points):
                    continue
            except Exception:
                continue

        if day:
            rdays = r.get("days") or []
            if day not in rdays:
                continue

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

        out.append(r)

    # Sort by start time then course_code
    def sort_key(x):
        return (
            10**9 if x.get("start_minutes") is None else x["start_minutes"],
            x.get("course_code") or "",
        )

    return sorted(out, key=sort_key)


# ----------------- CLI driver (for smoke tests / acceptance) -----------------

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
        # These asserts match the original acceptance spec (fixture-based).
        # If your real scrape doesn't have a 2-pt Monday 16:30 class, this block won't run
        # unless you set ENV=TEST_FILTERS.
        assert all(float(r["credits"]) == 2.0 for r in out), "Not all results are 2 credits"
        assert all("M" in (r["days"] or []) for r in out), "Not all results are on Monday"
        out2 = filter_rows(rows, points=2, day="M", time_mode="overlaps", time_hhmm="16:30")
        assert len(out2) >= len(out), "Overlaps set should be >= starts_at set"
        print("ACCEPTANCE FILTERS: OK")
    else:
        # --- Live Streamlit app ---
        import sys
        import streamlit as st

        st.set_page_config(page_title="Columbia Course Finder (POC)", layout="wide")
        st.title("Columbia Course Finder — Directory of Classes (POC)")

        # Resolve input path passed via "streamlit run src/transformers.py -- --input data/sample_output.json"
        input_path = "data/sample_output.json"
        if "--" in sys.argv:
            i = sys.argv.index("--")
            # Simple arg parse for --input
            j = i + 1
            while j + 1 < len(sys.argv):
                if sys.argv[j] == "--input":
                    input_path = sys.argv[j + 1]
                    break
                j += 1

        # Load & flatten (ensure we always have rows, not nested courses)
        courses = read_json(input_path)
        rows = to_rows(courses)

        # Sidebar filters
        st.sidebar.header("Filters")

        # Optional points filter (off by default to avoid zero results)
        pts_enabled = st.sidebar.checkbox("Filter by points (credits)?", value=False)
        pts_value = st.sidebar.number_input(
            "Points (credits)",
            min_value=0.0, max_value=10.0, value=2.0, step=0.5,
            disabled=not pts_enabled
        )
        pts = pts_value if pts_enabled else None

        day = st.sidebar.selectbox("Day", options=["", "M", "Tu", "W", "Th", "F", "Sa", "Su"], index=0)
        day = day or None

        mode = st.sidebar.radio("Time mode", options=["starts_at", "overlaps"], index=0)

        # Optional time filter (off by default). Streamlit time_input cannot be None in all versions.
        time_enabled = st.sidebar.checkbox("Filter by time?", value=False)
        time_hhmm: Optional[str] = None
        if time_enabled:
            default_time = datetime.time(16, 30)  # 4:30 PM as a handy default
            time_label = st.sidebar.time_input("Time (24h)", value=default_time, step=300)
            time_hhmm = time_label.strftime("%H:%M")

        # Apply filters
        filtered = filter_rows(rows, points=pts, day=day, time_mode=mode, time_hhmm=time_hhmm)

        # Diagnostics to help you confirm shapes quickly
        with st.expander("Diagnostics", expanded=False):
            st.write({
                "courses_count": len(courses),
                "rows_count": len(rows),
                "filtered_count": len(filtered),
                "using_points": pts if pts is not None else "(none)",
                "using_day": day if day else "(none)",
                "time_mode": mode,
                "time_hhmm": time_hhmm if time_hhmm else "(none)"
            })
            if rows:
                st.text(f"Row keys sample: {list(rows[0].keys())}")

        st.caption(f"{len(filtered)} matching meeting(s). Sorted by start time.")

        show_cols = [
            "course_code", "title", "credits", "term", "section", "crn",
            "instructor", "days", "start_time", "end_time", "location", "short_desc"
        ]

        def _ensure_table(data: List[Dict[str, Any]], cols: List[str]) -> pd.DataFrame:
            """Create a stable table that never KeyErrors, even when empty or missing columns."""
            df = pd.DataFrame(data)
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            return df[cols]

        table = _ensure_table(filtered, show_cols)

        if table.empty:
            st.warning(
                "No results for the current filters. "
                "Tips: uncheck points, change day, switch time mode to 'overlaps', "
                "or pick a different time."
            )

        st.dataframe(table, use_container_width=True)
        st.download_button(
            "Download results (JSON)",
            data=json.dumps(filtered, ensure_ascii=False, indent=2),
            file_name="results.json",
            mime="application/json",
        )
