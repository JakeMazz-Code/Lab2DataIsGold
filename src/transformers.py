# src/transformers.py
from __future__ import annotations
import argparse, json, os
from typing import Any, Dict, List, Optional, Union
from dateutil import parser as dtparser
import pandas as pd
from validators import Course, read_json

DAY_ORDER = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]

def parse_time_to_24h(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    s = s.strip()
    if not s or s.upper() in {"TBA", "ARR", "ARRANGED"}: return None
    s = s.replace("Noon", "12:00 PM").replace("noon", "12:00 PM")
    s = s.replace("Midnight", "12:00 AM").replace("midnight", "12:00 AM")
    try:
        t = dtparser.parse(s, fuzzy=True); return t.strftime("%H:%M")
    except Exception:
        if s.endswith("a") or s.endswith("p"):
            try:
                t = dtparser.parse(s + "m", fuzzy=True); return t.strftime("%H:%M")
            except Exception: return None
        return None

def normalize_credits(raw: Union[str, int, float, None]) -> Union[int, float, str, None]:
    if raw is None: return None
    if isinstance(raw, (int, float)): return raw
    s = str(raw).strip()
    try: return float(s) if "." in s else int(s)
    except Exception: return s

def hhmm_to_minutes(s: Optional[str]) -> Optional[int]:
    if s is None: return None
    hh, mm = s.split(":"); return int(hh)*60 + int(mm)

def to_rows(courses: List[Course]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for c in courses:
        for sec in c.sections:
            if not sec.meetings:
                rows.append({
                    "university": c.university, "course_code": c.course_code, "title": c.title,
                    "credits": normalize_credits(c.credits), "term": sec.term, "section": sec.section,
                    "crn": sec.crn, "instructor": sec.instructor, "days": [], "start_time": None,
                    "end_time": None, "start_minutes": None, "end_minutes": None, "location": None,
                    "short_desc": (c.description or "")[:140].strip(),
                })
            for m in sec.meetings:
                st, et = m.start_time, m.end_time
                rows.append({
                    "university": c.university, "course_code": c.course_code, "title": c.title,
                    "credits": normalize_credits(c.credits), "term": sec.term, "section": sec.section,
                    "crn": sec.crn, "instructor": sec.instructor, "days": m.days, "start_time": st,
                    "end_time": et, "start_minutes": hhmm_to_minutes(st) if st else None,
                    "end_minutes": hhmm_to_minutes(et) if et else None,
                    "location": " ".join(filter(None, [m.location.building if m.location else None,
                                                       m.location.room if m.location else None])) if m.location else None,
                    "short_desc": (c.description or "")[:140].strip(),
                })
    return rows

def filter_rows(rows: List[Dict[str, Any]],
                points: Optional[Union[int, float]] = None,
                day: Optional[str] = None,
                time_mode: str = "starts_at",
                time_hhmm: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    tmin = None if not time_hhmm else (int(time_hhmm[:2])*60 + int(time_hhmm[3:]))
    for r in rows:
        if points is not None:
            cr = r["credits"]
            try:
                if float(cr) != float(points): continue
            except Exception:
                continue
        if day and (not r["days"] or day not in r["days"]): continue
        if tmin is not None:
            sm, em = r.get("start_minutes"), r.get("end_minutes")
            if sm is None or em is None: continue
            if time_mode == "starts_at":
                if sm != tmin: continue
            else:
                if not (sm <= tmin <= em): continue
        out.append(r)
    def sort_key(x):
        return (10**9 if x["start_minutes"] is None else x["start_minutes"],
                x["course_code"] or "")
    return sorted(out, key=sort_key)

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
    res = filter_rows(rows, points=args.points, day=args.day, time_mode=args.mode, time_hhmm=args.time)
    print(json.dumps(res[:5], indent=2))

if __name__ == "__main__":
    if os.getenv("ENV") == "TEST_FILTERS":
        courses = read_json("data/sample_output.json")
        rows = to_rows(courses)
        out = filter_rows(rows, points=2, day="M", time_mode="starts_at", time_hhmm="16:30")
        assert any(r["course_code"].startswith("COMS") for r in out)
        assert all(float(r["credits"]) == 2.0 for r in out)
        assert all("M" in r["days"] for r in out)
        assert not any("STAT" in r["course_code"] for r in out)
        print("OK: starts_at 16:30 Monday, 2 points")
        out2 = filter_rows(rows, points=2, day="M", time_mode="overlaps", time_hhmm="16:30")
        assert any("COMS" in r["course_code"] for r in out2)
        assert any("STAT" in r["course_code"] for r in out2)
        print("OK: overlaps 16:30 Monday, 2 points")
    else:
        import streamlit as st
        st.set_page_config(page_title="Columbia Course Finder (POC)", layout="wide")
        st.title("Columbia Course Finder — Directory of Classes (POC)")
        import sys
        input_path = "data/sample_output.json"
        if "--" in sys.argv:
            i = sys.argv.index("--")
            for j in range(i + 1, len(sys.argv)):
                if sys.argv[j] == "--input" and j + 1 < len(sys.argv):
                    input_path = sys.argv[j + 1]
        courses = read_json(input_path)
        rows = to_rows(courses)
        df = pd.DataFrame(rows)
        st.sidebar.header("Filters")
        pts = st.sidebar.number_input("Points (credits)", min_value=0.0, max_value=10.0, value=2.0, step=0.5)
        day = st.sidebar.selectbox("Day", options=["", "M", "Tu", "W", "Th", "F", "Sa", "Su"], index=1)
        mode = st.sidebar.radio("Time mode", options=["starts_at", "overlaps"], index=0)
        time_label = st.sidebar.time_input("Time (24h)", value=None, step=300)
        time_hhmm = time_label.strftime("%H:%M") if time_label else None
        filtered = filter_rows(rows, points=pts, day=day or None, time_mode=mode, time_hhmm=time_hhmm)
        st.caption(f"{len(filtered)} matching meeting(s). Sorted by start time.")
        show_cols = ["course_code","title","credits","term","section","crn","instructor","days","start_time","end_time","location","short_desc"]
        st.dataframe(pd.DataFrame(filtered)[show_cols])
        st.download_button("Download results (JSON)", data=json.dumps(filtered, ensure_ascii=False, indent=2),
                           file_name="results.json", mime="application/json")
