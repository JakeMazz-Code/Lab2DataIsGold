from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

@dataclass
class Location:
    campus: Optional[str] = None
    building: Optional[str] = None
    room: Optional[str] = None

@dataclass
class Section:
    university: str
    term: str                     # "Fall 2025"
    subject: str                  # "COMS"
    number: str                   # "W4701"
    course_code: str              # "COMS W4701"
    section: str                  # "001", "R01", etc.
    crn: Optional[str] = None
    title: Optional[str] = None
    credits_min: Optional[float] = None
    credits_max: Optional[float] = None
    credits: Optional[float] = None       # if fixed
    days: List[str] = field(default_factory=list)
    start_time: Optional[str] = None      # "HH:MM"
    end_time: Optional[str] = None
    location: Location = field(default_factory=Location)
    instructor: Optional[str] = None
    component: Optional[str] = None       # "LECTURE", "SEMINAR", "LAB", "RECITATION", ...
    is_recitation: bool = False
    parent_course_code: Optional[str] = None
    detail_url: Optional[str] = None
    short_desc: Optional[str] = None
    status: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        """Flat row for DataFrame display."""
        return {
            "course_code": self.course_code,
            "title": self.title,
            "credits": self.credits if self.credits is not None else self.credits_max or self.credits_min,
            "credits_min": self.credits_min,
            "credits_max": self.credits_max,
            "term": self.term,
            "subject": self.subject,
            "number": self.number,
            "section": self.section,
            "crn": self.crn,
            "instructor": self.instructor,
            "component": self.component,
            "is_recitation": self.is_recitation,
            "parent_course_code": self.parent_course_code,
            "days": ", ".join(self.days) if self.days else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "location": " ".join([x for x in [self.location.building, self.location.room] if x]) if self.location else None,
            "detail_url": self.detail_url,
            "short_desc": self.short_desc,
            "status": self.status,
        }

def normalize_sections(raw_sections: List[Dict[str, Any]]) -> List[Section]:
    """Convert raw dicts (from scraper) into validated Section dataclass instances."""
    normalized: List[Section] = []
    for r in raw_sections:
        loc = r.get("location") or {}
        section = Section(
            university=r.get("university", "Columbia University"),
            term=r.get("term"),
            subject=r.get("subject"),
            number=r.get("number"),
            course_code=r.get("course_code"),
            section=r.get("section"),
            crn=r.get("crn"),
            title=r.get("title"),
            credits_min=r.get("credits_min"),
            credits_max=r.get("credits_max"),
            credits=r.get("credits"),
            days=r.get("days") or [],
            start_time=r.get("start_time"),
            end_time=r.get("end_time"),
            location=Location(
                campus=loc.get("campus"),
                building=loc.get("building"),
                room=loc.get("room"),
            ),
            instructor=r.get("instructor"),
            component=r.get("component"),
            is_recitation=bool(r.get("is_recitation")),
            parent_course_code=r.get("parent_course_code"),
            detail_url=r.get("detail_url"),
            short_desc=r.get("short_desc"),
            status=r.get("status"),
        )
        normalized.append(section)
    return normalized

def flatten_for_display(sections: List[Section]) -> List[Dict[str, Any]]:
    """List of rows for DataFrame."""
    return [s.to_row() for s in sections]

DISPLAY_COLS = [
    "course_code", "title", "credits", "term", "subject", "number",
    "section", "crn", "instructor", "component", "is_recitation",
    "parent_course_code", "days", "start_time", "end_time", "location",
    "detail_url"
]

def write_json(path: str, sections: List[Section]) -> None:
    payload = [asdict(s) for s in sections]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
