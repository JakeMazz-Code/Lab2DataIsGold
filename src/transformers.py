from __future__ import annotations

import os
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import requests
import streamlit as st

from scraper import (
    discover_subjects_for_term,
    scrape_many,
    term_to_sis_code,
    term_human,
)
from validators import normalize_sections, flatten_for_display, DISPLAY_COLS, write_json

# ----------------
# Page config & UI
# ----------------
st.set_page_config(
    page_title="Columbia Course Finder (Demo)",
    page_icon="🎓",
    layout="wide",
)

# Subtle CSS polish (slightly larger top padding so the spinner isn't obscured)
st.markdown("""
<style>
.block-container { padding-top: 1.15rem; padding-bottom: 2rem; }
.small-muted { color: #6b7280; font-size: 0.9rem; }
.badge { display:inline-block; padding: 0.1rem 0.45rem; border-radius: 0.35rem; background:#eef2ff; margin-right:0.25rem; font-size:0.85rem; }
.rec-badge { background:#fef3c7; }
.lec-badge { background:#dcfce7; }
.lab-badge { background:#e0f2fe; }
.semi-badge { background:#fce7f3; }
a:link, a:visited { color: #2563eb; text-decoration: none;}
a:hover { text-decoration: underline; }
.stProgress > div > div > div > div { background-color: #10b981; }
hr { border: none; border-top: 1px solid #e5e7eb; margin: 0.75rem 0 1rem; }
.kpi-card { background: #fafafa; border: 1px solid #eee; padding: 0.75rem 1rem; border-radius: 0.5rem; }
</style>
""", unsafe_allow_html=True)

# --------------
# Cache helpers
# --------------
@st.cache_data(show_spinner=False, ttl=60*60)  # 1 hour
def cached_discover_subjects(term: str) -> List[Dict[str, str]]:
    session = requests.Session()
    return discover_subjects_for_term(term, session)

@st.cache_data(show_spinner=True, ttl=60*5)  # 5 min
def cached_scrape(subjects: List[str], term: str) -> List[Dict]:
    session = requests.Session()
    return scrape_many(subjects, term, session)

# -----------------
# Helper functions
# -----------------
WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def ensure_display_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in set(DISPLAY_COLS) - set(out.columns):
        out[c] = None
    return out.reindex(columns=DISPLAY_COLS)

def compute_metrics(df: pd.DataFrame) -> Dict[str, int]:
    return {
        "sections": len(df),
        "courses": df["course_code"].nunique() if "course_code" in df.columns else 0,
        "subjects": df["subject"].nunique() if "subject" in df.columns else 0,
        "recitations": int((df.get("is_recitation", pd.Series(dtype=bool)) == True).sum()),
        "primaries": int((df.get("is_recitation", pd.Series(dtype=bool)) == False).sum()),
    }

def explode_days(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        days_raw = r.get("days") or ""
        days = [d.strip() for d in str(days_raw).split(",") if d.strip()]
        for d in days:
            rows.append({
                "course_code": r.get("course_code"),
                "is_recitation": r.get("is_recitation"),
                "day": d,
                "start_time": r.get("start_time"),
                "end_time": r.get("end_time"),
                "credits": r.get("credits") if pd.notnull(r.get("credits")) else (r.get("credits_max") or r.get("credits_min")),
                "instructor": r.get("instructor"),
                "building": (r.get("location") or ""),
                "component": r.get("component"),
            })
    return pd.DataFrame(rows)

def hhmm_to_hour(hhmm: Optional[str]) -> Optional[float]:
    if hhmm is None or pd.isna(hhmm): return None
    try:
        h, m = [int(x) for x in str(hhmm).split(":")]
        return h + m / 60.0
    except Exception:
        return None

def make_pipeline_dot() -> str:
    return r"""
digraph G {
    rankdir=LR;
    node [shape=roundrect, style=filled, color="#4f46e5", fillcolor="#eef2ff", fontname="Helvetica"];
    edge [color="#9ca3af"];

    A [label="1) Discover subjects\n(A–Z pages for chosen term)"];
    B [label="2) Scrape selections\n(Subject pages → plain text)"];
    C [label="3) Parse sections\n(Number, Sec, Points, Day/Time, Room,\nBuilding, Faculty)"];
    D [label="4) Link recitations\n(R## or 0 points → parent lecture)"];
    E [label="5) Normalize & cache\n(validated schema)"];
    F [label="6) Filter & browse\n(credits, days, time, text)"];
    G [label="7) Visualize & export\n(KPIs, charts, deck, CSV/JSON)"];

    A -> B -> C -> D -> E -> F -> G;
}
"""

def _to_float(x) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(x)
    except Exception:
        return None

def credit_bounds(row: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    c  = _to_float(row.get("credits"))
    cmin = _to_float(row.get("credits_min"))
    cmax = _to_float(row.get("credits_max"))

    if c is not None:
        return c, c
    if cmin is None and cmax is None:
        return None, None
    if cmin is None:
        cmin = cmax
    if cmax is None:
        cmax = cmin
    if cmax < cmin:
        cmin, cmax = cmax, cmin
    return cmin, cmax

def build_html_deck(term_label: str, metrics: Dict[str, int], sample_html_table: str) -> str:
    """
    A self-contained, single-file HTML "deck":
      • slide 1: title + term
      • slide 2: pipeline steps (bullets)
      • slide 3: key KPIs (sections, courses, subjects, primaries, recitations)
      • slide 4: sample results table
    No external assets; easy to email or attach to the demo record.
    """
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Columbia Course Finder — Demo Deck</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color:#111827; }}
  .slide {{ width: 100%; height: 100vh; padding: 4rem 6vw; box-sizing: border-box; display:flex; flex-direction:column; justify-content:center; }}
  h1,h2,h3 {{ margin: 0 0 0.75rem; }}
  .muted {{ color:#6b7280; }}
  .kpis {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; margin-top: 1rem; }}
  .card {{ border:1px solid #e5e7eb; border-radius:8px; padding: 12px; background:#fafafa; }}
  .table-wrap {{ max-height: 50vh; overflow:auto; border:1px solid #e5e7eb; border-radius:8px; }}
  footer {{ position: fixed; bottom: 10px; right: 16px; font-size: 12px; color:#9ca3af; }}
</style>
</head>
<body>

<section class="slide">
  <h1>Columbia Course Finder</h1>
  <h3 class="muted">Term: {term_label}</h3>
  <p>A scraping demo that discovers subjects, scrapes the Directory of Classes, links recitations to their parent lectures, and presents a student-friendly search UI.</p>
</section>

<section class="slide">
  <h2>Pipeline</h2>
  <ol>
    <li>Discover subjects for the chosen term (A–Z index)</li>
    <li>Scrape selected or ALL subjects (plain text listings)</li>
    <li>Parse sections (number, points, day/time, room, instructor)</li>
    <li>Link recitations (0 points or R##) to parent lectures</li>
    <li>Normalize schema → dashboard filters & visuals</li>
  </ol>
</section>

<section class="slide">
  <h2>Key metrics</h2>
  <div class="kpis">
    <div class="card"><strong>Sections</strong><div>{metrics["sections"]}</div></div>
    <div class="card"><strong>Courses</strong><div>{metrics["courses"]}</div></div>
    <div class="card"><strong>Subjects</strong><div>{metrics["subjects"]}</div></div>
    <div class="card"><strong>Primaries</strong><div>{metrics["primaries"]}</div></div>
    <div class="card"><strong>Recitations</strong><div>{metrics["recitations"]}</div></div>
  </div>
</section>

<section class="slide">
  <h2>Sample results</h2>
  <div class="table-wrap">{sample_html_table}</div>
  <p class="muted">Tip: Full CSV/JSON available from the Export tab.</p>
</section>

<footer>Generated {datetime.utcnow().isoformat(timespec="seconds")}Z</footer>
</body>
</html>"""

# ----------------
# Sidebar controls
# ----------------
st.sidebar.title("🎓 Columbia Course Finder")
st.sidebar.markdown("**Proof-of-concept:** discover → scrape → filter → visualize → export.")

term_input = st.sidebar.selectbox("Term", ["Fall 2025", "Summer 2025", "Spring 2026"], index=0)
term_label = term_human(term_input)
term_code = term_to_sis_code(term_input)

demo_mode = st.sidebar.toggle("🎬 Demo Mode (recording‑friendly)", value=True,
                              help="Uses curated defaults (e.g., COMS/STAT) and caps subjects for a fast, reproducible demo.")

with st.spinner("Discovering subjects for the term…"):
    subjects_list = cached_discover_subjects(term_input)
subject_options = [f"{s['code']} — {s['name']}" for s in subjects_list]
code_by_option = {f"{s['code']} — {s['name']}": s["code"] for s in subjects_list}
st.sidebar.success(f"Loaded {len(subjects_list)} subjects for {term_label}")

st.sidebar.markdown("---")

if demo_mode:
    st.sidebar.info("Demo suggestion: scrape **COMS** and **STAT** first, then try **ALL**.")
    default_sel = [opt for opt in subject_options if opt.startswith("COMS")] + \
                  [opt for opt in subject_options if opt.startswith("STAT")]
    default_sel = default_sel[:2] or subject_options[:2]
    cap_default = 8
else:
    default_sel = [opt for opt in subject_options if opt.startswith("COMS")]
    cap_default = 10

all_flag = st.sidebar.checkbox("Scrape **ALL** subjects", value=False)
selected_options = [] if all_flag else st.sidebar.multiselect(
    "Pick subjects (or choose ALL):",
    options=subject_options,
    default=default_sel
)

max_subjects = st.sidebar.number_input("Cap subjects (testing)", min_value=1, step=1, value=cap_default,
                                       help="Use to test a smaller scrape when 'ALL' is selected.")
go = st.sidebar.button("🚀 Scrape now")

if "sections_raw" not in st.session_state:
    st.session_state["sections_raw"] = []
if "sections_df" not in st.session_state:
    st.session_state["sections_df"] = pd.DataFrame()

if go:
    if all_flag:
        subject_codes = [s["code"] for s in subjects_list][:max_subjects]
    else:
        if not selected_options:
            st.warning("Please select at least one subject or check **ALL**.")
            st.stop()
        subject_codes = [code_by_option[o] for o in selected_options]

    st.info(f"Scraping **{len(subject_codes)}** subject(s)…")
    with st.spinner("Scraping…"):
        raw = cached_scrape(subject_codes, term_input)

    sections = normalize_sections(raw)
    rows = flatten_for_display(sections)
    df = pd.DataFrame(rows)
    df = ensure_display_cols(df)

    st.session_state["sections_raw"] = raw
    st.session_state["sections_df"] = df

# ------------------------
# Main tabs (demo-friendly)
# ------------------------
st.title("Columbia Course Finder")
st.caption(f"Term: **{term_label}** • Data source: Directory of Classes (DOC) — subject A–Z → per‑term → plain‑text listings. "
           "Recitations are linked to parent lectures when disclosed on section detail pages.")

tab_search, tab_visuals, tab_how, tab_export = st.tabs(["🔎 Search", "📊 Visuals", "🛠️ How it works", "📤 Export"])

# ===========
# SEARCH TAB
# ===========
with tab_search:
    if st.session_state["sections_df"].empty:
        st.info("No results yet. Choose subjects on the left and click **Scrape now**.")
    else:
        st.subheader("Filters")

        f1, f2, f3, f4 = st.columns([1, 1, 2, 2])
        with f1:
            credits_min = st.number_input("Min credits", value=0.0, step=0.5)
        with f2:
            credits_max = st.number_input("Max credits", value=6.0, step=0.5)

        with f3:
            WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            day_choices = st.multiselect("Days", WEEKDAY_ORDER, default=[], help="Filter by meeting days.")
        with f4:
            time_filter = st.checkbox("Filter by time window", value=False)
            if time_filter:
                c1, c2 = st.columns(2)
                with c1:
                    start_after = st.time_input("Start at or after", value=dtime(0, 0))
                with c2:
                    end_before = st.time_input("End at or before", value=dtime(23, 59))
            else:
                start_after = None
                end_before = None

        include_recitations_in_time = st.checkbox(
            "Apply day/time filter to **recitations as well**",
            value=False,
            help="If off, day/time filter applies only to primary sections (is_recitation==False)."
        )
        query = st.text_input("Keyword (title/instructor/building)", value="")

        df = st.session_state["sections_df"].copy()

        bounds = df.apply(lambda r: pd.Series(credit_bounds(r), index=["__cmin", "__cmax"]), axis=1)
        df = pd.concat([df, bounds], axis=1)

        def credits_overlap(row) -> bool:
            cmin, cmax = row.get("__cmin"), row.get("__cmax")
            if pd.isna(cmin) and pd.isna(cmax):
                return True
            if pd.isna(cmin): cmin = cmax
            if pd.isna(cmax): cmax = cmin
            return not (cmax < credits_min or cmin > credits_max)

        mask = df.apply(credits_overlap, axis=1)

        def row_matches_day(row) -> bool:
            if not day_choices:
                return True
            days = [d.strip() for d in str(row.get("days") or "").split(",") if d.strip()]
            if not days:
                return False
            return any(d in days for d in day_choices)

        def hhmm_to_minutes(hhmm: str) -> Optional[int]:
            try:
                h, m = [int(x) for x in str(hhmm).split(":")]
                return h * 60 + m
            except Exception:
                return None

        def row_matches_time(row) -> bool:
            if not time_filter:
                return True
            s, e = row.get("start_time"), row.get("end_time")
            s_min, e_min = hhmm_to_minutes(s), hhmm_to_minutes(e)
            if s_min is None or e_min is None:
                return False
            if start_after is not None and s_min < (start_after.hour * 60 + start_after.minute):
                return False
            if end_before is not None and e_min > (end_before.hour * 60 + end_before.minute):
                return False
            return True

        if include_recitations_in_time:
            mask &= df.apply(lambda r: row_matches_day(r) and row_matches_time(r), axis=1)
        else:
            only_primary = df.get("is_recitation", False) == False
            day_time_mask = df.apply(lambda r: row_matches_day(r) and row_matches_time(r), axis=1)
            mask &= (~only_primary) | (only_primary & day_time_mask)

        if query.strip():
            q = query.strip().lower()
            def matches_q(row) -> bool:
                hay = " ".join([
                    str(row.get("title") or ""),
                    str(row.get("instructor") or ""),
                    str(row.get("location") or ""),
                    str(row.get("course_code") or ""),
                ]).lower()
                return q in hay
            mask &= df.apply(matches_q, axis=1)

        filtered = df[mask].copy().reset_index(drop=True)

        st.markdown(f"**{len(filtered)}** matching sections")
        st.dataframe(filtered.reindex(columns=DISPLAY_COLS), use_container_width=True, hide_index=True)

        st.subheader("Browse by Course (expand for sections & recitations)")
        grouped = filtered.groupby("course_code", sort=True) if "course_code" in filtered.columns else []
        for course_code, g in grouped:
            title = g["title"].dropna().unique() if "title" in g.columns else []
            pretty_title = title[0] if len(title) else ""
            chip = f"<span class='badge lec-badge'>{pretty_title}</span>"
            st.markdown(f"### {course_code} &nbsp; {chip}", unsafe_allow_html=True)

            with st.expander("Show sections"):
                prim = g[g.get("is_recitation", False) == False].copy()
                recs = g[g.get("is_recitation", False) == True].copy()

                if not prim.empty:
                    st.markdown("**Primary**")
                    cols = ["section", "crn", "component", "instructor",
                            "days", "start_time", "end_time", "location", "detail_url"]
                    prim_display = prim[[c for c in cols if c in prim.columns]].rename(columns={"detail_url": "DOC link"})
                    if "DOC link" in prim_display.columns:
                        prim_display["DOC link"] = prim_display["DOC link"].apply(lambda u: f"[open]({u})" if pd.notnull(u) else "")
                    st.dataframe(prim_display, use_container_width=True, hide_index=True)
                else:
                    st.write("_No primary sections shown in current filter._")

                if not recs.empty:
                    st.markdown("**Linked recitations/labs/discussions**")
                    cols = ["section", "parent_course_code", "component", "instructor",
                            "days", "start_time", "end_time", "location", "detail_url"]
                    rec_display = recs[[c for c in cols if c in recs.columns]].rename(columns={"detail_url": "DOC link"})
                    if "DOC link" in rec_display.columns:
                        rec_display["DOC link"] = rec_display["DOC link"].apply(lambda u: f"[open]({u})" if pd.notnull(u) else "")
                    st.dataframe(rec_display, use_container_width=True, hide_index=True)
                else:
                    st.write("_No recitations linked or shown in current filter._")

# ===========
# VISUALS TAB
# ===========
with tab_visuals:
    if st.session_state["sections_df"].empty:
        st.info("Scrape some subjects to see visuals.")
    else:
        st.subheader("Pipeline overview")
        st.graphviz_chart(make_pipeline_dot(), use_container_width=True)

        st.subheader("Key metrics")
        met = compute_metrics(st.session_state["sections_df"])
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Sections", met["sections"])
        c2.metric("Courses", met["courses"])
        c3.metric("Subjects", met["subjects"])
        c4.metric("Primaries", met["primaries"])
        c5.metric("Recitations", met["recitations"])

        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("Distributions & schedule")

        base_df = st.session_state["sections_df"].copy()
        exploded = explode_days(base_df)
        if exploded.empty:
            st.info("No day/time data available for charts.")
        else:
            exploded["start_hour"] = exploded["start_time"].apply(hhmm_to_hour)
            exploded = exploded[exploded["day"].isin(WEEKDAY_ORDER)]

            prim = exploded[exploded.get("is_recitation", False) == False]
            if not prim.empty:
                weekday_counts = prim.groupby("day").size().reindex(WEEKDAY_ORDER, fill_value=0).reset_index(name="count")
                st.markdown("**Sections by weekday (primaries)**")
                st.bar_chart(weekday_counts.set_index("day"))

            credits_df = exploded.dropna(subset=["credits"])
            if not credits_df.empty:
                st.markdown("**Credits distribution**")
                hist = alt.Chart(credits_df).mark_bar().encode(
                    x=alt.X("credits:Q", bin=alt.Bin(step=1), title="Credits"),
                    y=alt.Y("count()", title="Sections")
                ).properties(height=220, width="container")
                st.altair_chart(hist, use_container_width=True)

            heat_df = exploded.dropna(subset=["start_hour"])
            if not heat_df.empty:
                st.markdown("**Schedule heatmap (start hours by weekday)**")
                heat = alt.Chart(heat_df).mark_rect().encode(
                    x=alt.X("day:N", sort=WEEKDAY_ORDER, title="Day"),
                    y=alt.Y("start_hour:Q", bin=alt.Bin(step=1), title="Start hour"),
                    color=alt.Color("count():Q", title="Sections"),
                    tooltip=["day:N", alt.Tooltip("start_hour:Q", format=".1f"), alt.Tooltip("count():Q")]
                ).properties(height=260, width="container")
                st.altair_chart(heat, use_container_width=True)

# =================
# HOW IT WORKS TAB
# =================
with tab_how:
    st.subheader("What the app does")
    st.markdown("""
1. **Discover** the official subject list for your chosen term from Columbia's DOC A–Z index.
2. **Scrape** either ALL or selected subjects using the **plain‑text listings** (stable columns).
3. **Parse** sections: number, section, points (credits), day/time, room, building, instructor.
4. **Link recitations** (0 credits or `R##`) back to their parent lectures (from section detail pages, when disclosed).
5. **Normalize** into a consistent schema for filtering/searching.
6. **Visualize & export** (KPIs, charts, CSV/JSON, self‑contained HTML deck).
""")
    st.info("Tip for recording: enable **Demo Mode** in the sidebar, scrape COMS/STAT, then show the Visuals tab and expand a few courses.")

# ===========
# EXPORT TAB
# ===========
with tab_export:
    st.subheader("Save / Download / Generate deck")

    if st.session_state["sections_df"].empty:
        st.info("Scrape results first to export.")
    else:
        colA, colB, colC = st.columns([1,1,2])

        with colA:
            if st.button("💾 Save full JSON to data/columbia_sections.json"):
                sections = normalize_sections(st.session_state["sections_raw"])
                os.makedirs("data", exist_ok=True)
                write_json("data/columbia_sections.json", sections)
                st.success("Saved to data/columbia_sections.json")

        with colB:
            csv = st.session_state["sections_df"].to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download all sections (CSV)", data=csv,
                               file_name="all_sections.csv", mime="text/csv")

        with colC:
            df = st.session_state["sections_df"]
            metrics = compute_metrics(df)
            sample_cols = [c for c in ["course_code", "title", "credits", "days", "start_time", "end_time", "instructor", "location"] if c in df.columns]
            sample = df[sample_cols].head(18)
            sample_html = sample.to_html(index=False, escape=False)

            deck_html = build_html_deck(term_label, metrics, sample_html)

            os.makedirs("docs", exist_ok=True)
            out_path = "docs/demo_deck.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(deck_html)

            st.download_button("🎞️ Download demo deck (HTML)", data=deck_html.encode("utf-8"),
                               file_name="demo_deck.html", mime="text/html")
            st.caption("Also written to **docs/demo_deck.html**")
