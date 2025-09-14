# src/validators.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, validator, root_validator
import json
import re
import os

DAY_TOKENS = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]

def _split_compact_days(s: str) -> List[str]:
    """
    Accepts Columbia-style compact day strings like:
      'MWF', 'TR', 'M', 'W', 'F', 'S', 'U', and mixed 'TuTh'.
    Mapping:
      M->M, T->Tu, W->W, R->Th, F->F, S->Sa, U->Su
    """
    s = (s or "").strip().upper().replace(" ", "").replace(".", "")
    if not s:
        return []
    out: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        nxt = s[i+1] if i + 1 < len(s) else ""
        # Two-letter tokens first
        if ch == "T" and nxt == "H":
            out.append("Th"); i += 2; continue
        if ch == "T" and nxt == "U":
            out.append("Tu"); i += 2; continue
        # Single letters
        if ch == "M": out.append("M"); i += 1; continue
        if ch == "T": out.append("Tu"); i += 1; continue
        if ch == "W": out.append("W"); i += 1; continue
        if ch == "R": out.append("Th"); i += 1; continue
        if ch == "F": out.append("F"); i += 1; continue
        if ch == "S": out.append("Sa"); i += 1; continue
        if ch == "U": out.append("Su"); i += 1; continue
        i += 1
    # Dedup preserving order
    seen = set(); dedup = []
    for d in out:
        if d not in seen:
            seen.add(d); dedup.append(d)
    return dedup

def _validate_time_str(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    if not re.match(r"^\d{2}:\d{2}$", s):
        raise ValueError(f"Time must be HH:MM (24h); got {s}")
    hh, mm = s.split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time range: {s}")
    return s

class Location(BaseModel):
    campus: Optional[str] = None
    building: Optional[str] = None
    room: Optional[str] = None

class Meeting(BaseModel):
    days: List[str]
    start_time: Optional[str] = None  # "HH:MM" 24h
    end_time: Optional[str] = None    # "HH:MM" 24h
    time_tba: bool = False
    location: Optional[Location] = None

    @validator("days", pre=True)
    def normalize_days(cls, v):
        if isinstance(v, str):
            v = _split_compact_days(v)
        v = [d.strip() for d in v or []]
        # Dedup preserve order; only keep known tokens
        out, seen = [], set()
        for d in v:
            if d in DAY_TOKENS and d not in seen:
                out.append(d); seen.add(d)
        return out

    @validator("start_time", "end_time", pre=True, always=True)
    def _validate_time(cls, v, values):
        time_tba = values.get("time_tba", False)
        if time_tba and v is None:
            return None
        return _validate_time_str(v) if v is not None else None

class Section(BaseModel):
    term: str
    crn: Optional[str] = None
    section: Optional[str] = None
    instructor: Optional[str] = None
    status: Optional[str] = None
    component: Optional[str] = None  # <-- NEW: Lecture / Recitation / Lab / Seminar ...
    meetings: List[Meeting] = []

class Course(BaseModel):
    university: str
    subject: str
    number: str
    course_code: str
    title: str
    credits: Union[int, float, str]
    description: Optional[str] = None
    prerequisites: Optional[str] = None
    sections: List[Section] = []

    @root_validator(pre=True)
    def coerce_credits(cls, values):
        cr = values.get("credits")
        if isinstance(cr, str):
            s = cr.strip()
            try:
                if s and s.replace(".", "", 1).isdigit():
                    values["credits"] = float(s) if "." in s else int(s)
            except Exception:
                pass
        return values

def to_jsonable(obj: Course) -> Dict[str, Any]:
    import json as _json
    return _json.loads(obj.json())

def write_json(path: str, courses: List[Course]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([json.loads(c.json()) for c in courses], f, ensure_ascii=False, indent=2)

def read_json(path: str) -> List[Course]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Course(**d) for d in data]

if __name__ == "__main__":
    assert _split_compact_days("MWF") == ["M", "W", "F"]
    assert _split_compact_days("TR") == ["Tu", "Th"]
    assert _split_compact_days("TuTh") == ["Tu", "Th"]
    print("validators.py basic checks: OK")
