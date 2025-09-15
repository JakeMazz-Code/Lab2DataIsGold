# src/bts_demo.py
from __future__ import annotations
import time, random
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

import streamlit as st

# ------------------ rerun shim (new/old Streamlit) ------------------
def _rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()  # type: ignore[attr-defined]
        except Exception:
            pass

# ------------------ Expanded technical steps (LEFT) ------------------
EXPLAIN_STEPS = [
    ("Step 1 — Discover subjects",
     "• Crawl A–Z index: https://doc.sis.columbia.edu/sel/subj-{A..Z}.html\n"
     "• Normalize the term (e.g., “Fall 2025” → `Fall2025`). Keep only anchors whose TEXT equals the term (no guessing).\n"
     "• Extract {CODE} from href `/subj/{CODE}/_{term}.html`; name = parent text before the term tokens."),
    ("Step 2 — Subject page",
     "• GET `/subj/{SUBJ}/_{term}.html` with a stable UA + polite throttle.\n"
     "• Resilient fetch (tenacity) for transient errors.\n"
     "• Find the 'plain text version' link; fallback to `/subj/{SUBJ}/_{term}_text.html`."),
    ("Step 3 — Plain text listing",
     "• Extract plain text via BeautifulSoup; locate header with `Number`, `Call#`, `Faculty`.\n"
     "• Build fixed-width slices from header label offsets → stable row parsing."),
    ("Step 4 — Parse rows",
     "• Row guard: emit a section only if `title` and (number|section|numeric Call#) exist.\n"
     "• Instructor continuation: if previous instructor ends with a comma, append current Faculty.\n"
     "• Time parsing (full-line first for ranges; else Time slice): normalize unicode dashes + 'to'.\n"
     "  Order: AM/PM range → 24h range → HHMM digits → single time → TBA. If line shows 'pm' but not 'am', coerce <12:00 to afternoon.\n"
     "• Days map: {'M','T','W','R','F','S','U'} → Mon..Sun.\n"
     "• Location repair: join 'To be' + 'announced'; move trailing letter from room to building if the building starts lowercase.\n"
     "• Credits: fixed or range."),
    ("Step 5 — Link recitations",
     "• Flag recitations (R## or RECITATION + zero credits).\n"
     "• Build detail URL `/subj/{SUBJ}/{NUMBER}-{TERMCODE}-{SEC}/`; parse parent lecture when disclosed.\n"
     "• Fallback: title-normalized match within the subject."),
    ("Step 6 — Normalize & cache",
     "• Emit per section: course_code, section, crn, title, credits(min/max), days, start/end (24h), location{building,room}, instructor, component, recitation flag, detail url.\n"
     "• Dataclass normalization + caching keep the UI responsive."),
    ("Step 7 — Visualize & export",
     "• Filters by day/time/keyword; expand sections & recitations; 'DOC link' for provenance.\n"
     "• Visuals: weekday counts (primaries), credits histogram, schedule heatmap.\n"
     "• Export: CSV and a one-file HTML demo deck (offline)."),
]

# ------------------ Simple in-memory buffer (RIGHT log) ------------------
@dataclass
class TraceBuffer:
    lines: List[str] = field(default_factory=list)
    def write(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.lines.append(f"[{ts}] {msg}")
    def dump_md(self, max_lines: int = 500) -> str:
        out = self.lines[-max_lines:]
        return "\n".join(f"- {ln}" for ln in out)

# ------------------ Page setup & CSS ------------------
st.set_page_config(page_title="Behind-the-scenes storyboard", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 12px; }
.step { margin: 0 0 .5rem 0; padding:.6rem .8rem; border-radius:10px; border:1px solid #e5e7eb; }
.step.past { background:#f8fafc; opacity: .95; }
.step.current { background:#eef2ff; border-color:#c7d2fe; box-shadow:0 0 0 2px #e0e7ff inset; }
.step.future { opacity: .45; }
.step h4 { margin:0 0 .25rem 0; font-size: 1.05rem; }
.step .body { white-space:pre-wrap; margin:.25rem 0 0 0; font-size:.94rem; line-height:1.25rem; }
.arrow { text-align:center; font-size:20px; color:#9ca3af; margin:.15rem 0; }
.small { color:#6b7280; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)

st.title("Behind-the-scenes storyboard (auto)")
st.caption("Place this window next to your main app. Steps auto-cycle; sample log is generated for COMS, STAT, APMA.")

# ------------------ Defaults & state ------------------
if "buf" not in st.session_state:
    st.session_state.buf = TraceBuffer()
if "curr_idx" not in st.session_state:
    st.session_state.curr_idx = 0
if "last_advance" not in st.session_state:
    st.session_state.last_advance = time.time()
if "log_phase" not in st.session_state:
    st.session_state.log_phase = 0  # 0=emit GET, 1=emit parsed
if "subj_idx" not in st.session_state:
    st.session_state.subj_idx = 0

SUBJECTS = ["COMS", "STAT", "APMA"]  # sample subjects for the right log

# ------------------ Controls (simple) ------------------
ctl_left, ctl_right = st.columns([2, 3])
with ctl_left:
    autoplay = st.toggle("▶ Auto-cycle steps", value=True)
    step_duration_ms = st.slider("Step duration (ms)", 800, 4000, 1800, 100)
    tick_interval_ms = st.slider("Log tick (ms)", 300, 2000, 650, 50)
with ctl_right:
    st.markdown("**Subjects:** " + ", ".join(SUBJECTS))
    if st.button("Reset storyboard"):
        st.session_state.curr_idx = 0
        st.session_state.last_advance = time.time()
        st.session_state.buf = TraceBuffer()
        st.session_state.log_phase = 0
        st.session_state.subj_idx = 0

st.markdown("---")

# ------------------ Layout: LEFT steps / RIGHT live log ------------------
LEFT, RIGHT = st.columns([2, 3], gap="large")

# ---- LEFT: render all steps; show details up to current; arrow between ----
with LEFT:
    curr = st.session_state.curr_idx
    for i, (title, body) in enumerate(EXPLAIN_STEPS):
        cls = "past" if i < curr else ("current" if i == curr else "future")
        arrow = "⬇️ " if i == curr else ""
        st.markdown(
            f'<div class="step {cls}"><h4>{arrow}{title}</h4>'
            f'{f"<div class=\'body\'>"+body+"</div>" if i <= curr else ""}</div>',
            unsafe_allow_html=True
        )
        if i < len(EXPLAIN_STEPS) - 1:
            st.markdown('<div class="arrow">⬇️</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="small">Term: <b>Fall 2025</b> &nbsp;•&nbsp; Subjects: {", ".join(SUBJECTS)}</div>',
        unsafe_allow_html=True
    )

# ---- RIGHT: live sample log ----
with RIGHT:
    st.subheader("Live trace")
    st.markdown(st.session_state.buf.dump_md(), unsafe_allow_html=False)

# ------------------ Auto-cycling + log generation ------------------
# Auto-advance the step index based on elapsed time
now = time.time()
if autoplay and (now - st.session_state.last_advance) * 1000 >= step_duration_ms:
    st.session_state.curr_idx = (st.session_state.curr_idx + 1) % len(EXPLAIN_STEPS)
    st.session_state.last_advance = now

# Generate a simple two-line cycle per subject: GET -> parsed
buf = st.session_state.buf
if st.session_state.log_phase == 0:
    code = SUBJECTS[st.session_state.subj_idx % len(SUBJECTS)]
    buf.write(f"• GET /subj/{code}/_Fall2025.html")
    st.session_state.log_phase = 1
else:
    code = SUBJECTS[st.session_state.subj_idx % len(SUBJECTS)]
    parsed = random.randint(18, 64)
    buf.write(f"  ↳ parsed {parsed} section(s) from {code}")
    st.session_state.subj_idx += 1
    st.session_state.log_phase = 0

st.session_state.buf = buf

# Wait a bit so humans can read the update, then rerun
time.sleep(tick_interval_ms / 1000.0)
_rerun()
