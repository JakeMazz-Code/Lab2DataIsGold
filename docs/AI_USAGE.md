# Prompts & Outcomes (Build Log)

> This document captures the **prompts that drove the largest design/implementation changes**, the **rationale**, and the **concrete outcomes** in the codebase. Use these as a “recipe” to reproduce or extend the project.

---

## 0) Test-Driven Acceptance “North Star”

**Prompt**  
*“I must be able to find **2-credit** classes on **Monday** around **4:30 PM** and see **instructor/title/location/start–end** plus a **DOC link** in the UI.”*

**Why it mattered**  
This defined what “done” looks like and drove all parsing/normalization requirements.

**Implementation Outcomes**  
- **Time normalization** to 24h `HH:MM`, duplicate single times, and “PM-only coercion” to avoid 00:10/00:55 ghosts.  
- **Days** canonicalization to `["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]`.  
- **Row guard** to prevent department banners from becoming courses.  
- **Location repair** (TBA join; Kravis/Diana letter fix).  
- Overlap predicate for time filter: `(end > filter_start) ∧ (start < filter_end)`.

**Files touched**  
- `src/scraper.py` — parsing & repairs  
- `src/validators.py` — normalized rows  
- `src/transformers.py` — filter logic

---

## 1) Authoritative Subject Discovery

**Prompt**  
*“Discover subjects **only** from Columbia’s A–Z term index. Keep anchors whose **TEXT equals** the normalized term (e.g., `Fall2025`). No hardcoded lists, no guessing.”*

**Why it mattered**  
Prevents scraping non-existent subjects and keeps us in sync with the official catalog.

**Implementation Outcomes**  
- `discover_subjects_for_term(term)`:  
  - Crawl `https://doc.sis.columbia.edu/sel/subj-{A..Z}.html`.  
  - Normalize “Fall 2025” → `Fall2025`.  
  - Retain only anchors whose text **exactly matches** the term.  
  - Extract `{CODE}` from `/subj/{CODE}/_{term}.html`.

**Files touched**  
- `src/scraper.py` (discovery)

---

## 2) Plain-Text Listing as Source of Truth

**Prompt**  
*“Ignore the dynamic Angular UI; fetch the **plain-text version** from each subject’s term page and parse **column-aligned** text.”*

**Why it mattered**  
Stability. The plain-text listing rarely changes and is easier to parse deterministically.

**Implementation Outcomes**  
- Subject page: `/subj/{SUBJ}/_{TERM}.html`  
- Follow the “**plain text version**” link (fallback to `_{TERM}_text.html`).  
- **Header-driven slicing**: build start/end indices for `Number/Sec/Call#/Pts/Title/Day/Time/Room/Building/Faculty`.

**Files touched**  
- `src/scraper.py` (`parse_subject_text_page` + `_detect_columns`)

---

## 3) Deterministic Row Guard

**Prompt**  
*“Do **not** emit department banners/headers. A real row must have a **non-empty title** and at least one of: **Number** or **Section** or **numeric Call#**.”*

**Why it mattered**  
Eliminates junk rows (e.g., “L App Activ / RECIT”) polluting the dataset.

**Implementation Outcomes**  
- `_is_real_course_row(number, sec, calln, title)` check in parsing loop.

**Files touched**  
- `src/scraper.py` (row guard)

---

## 4) Instructor Continuation Merge

**Prompt**  
*“If the prior row’s instructor ends with a **comma**, and the current ‘Faculty’ column has text, append it to complete the name.”*

**Why it mattered**  
DOC plain-text sometimes wraps names; this prevents truncated instructors (“Lee, Ey”).

**Implementation Outcomes**  
- Merge “Faculty” tail into the previous section’s `instructor` when detected.

**Files touched**  
- `src/scraper.py` (parsing post-slice heuristic)

---

## 5) Multi-Format Time Parsing (Full-Line-First, Safe Fallback)

**Prompt**  
*“Support these inputs: `1:10 PM–2:25 PM`, `1:10PM-2:25PM`, `1410-1525`, `13:10 to 14:25`, **single times** (`14:10`), and `TBA`.*  
*Accept **full-line** ranges only if **increasing**; otherwise fallback to the **Time** column slice. If a line mentions `pm` (not `am`), coerce <12:00 to afternoon.”*

**Why it mattered**  
Time was the hardest field; we needed solid ordering + safe fallback to avoid false positives.

**Implementation Outcomes**  
- `parse_timerange_any(line)` tries, in order:  
  1) **AM/PM range** (meridiem propagation)  
  2) **24h** range (`13:10-14:25`)  
  3) **HHMM** digits (`1410-1525`)  
  4) **Single time** → duplicate bounds  
  5) **TBA**  
- Use **full-line** only if `end > start`; otherwise parse the **Time** slice.  
- **PM-only coercion** for lines containing `pm` but not `am`.

**Files touched**  
- `src/scraper.py` (`parse_timerange_any`, `parse_time_label`, PM coercion)

---

## 6) Days Canonicalization

**Prompt**  
*“Map compact day tokens to full names: `MWF` → `Mon,Wed,Fri`, `TuTh` → `Tue,Thu` (don’t split `Tu` into `T`).”*

**Why it mattered**  
Needed stable filtering by weekday in the UI.

**Implementation Outcomes**  
- `_split_days(day_field)` mapping with canonical ordering.

**Files touched**  
- `src/scraper.py` (days mapping)  
- `src/transformers.py` (filters expect “Mon…Sun”)

---

## 7) Location Repair (TBA Join + Kravis/Diana Letter Shift)

**Prompt**  
*“Fix the common splits: room=`‘To be’` + building contains `‘announced’` ⇒ building=`‘To be announced’`, room=None.*  
*If room ends with a **single uppercase letter** and building **starts lowercase** (e.g., ‘620 K’ + ‘ravis Hall’), move letter to building (‘Kravis Hall’), trim room (‘620’).”*

**Why it mattered**  
Cleans up ugly splits in the plain-text rendering (common at Columbia).

**Implementation Outcomes**  
- `_repair_location(room, building)` applies both repairs.

**Files touched**  
- `src/scraper.py` (location normalization)

---

## 8) Recitation Linking

**Prompt**  
*“Flag recitations (`R##` or `RECITATION` with 0 credits). Build `detail_url` and parse parent lecture if the detail page says ‘Required recitation… enrolled in {SUBJ} {NUMBER}’. Otherwise, fallback to a title-normalized match.”*

**Why it mattered**  
Makes the UI more useful—students see the relationship between recitations and lectures.

**Implementation Outcomes**  
- `link_recitations(sections, term_code, session)` with detail-page regex and fallback title match.

**Files touched**  
- `src/scraper.py` (linker + URL builder)

---

## 9) Streamlit UI: Filters, Visuals, Export

**Prompt**  
*“Add filters (credits, days, optional time window, keyword), grouped course view with ‘DOC link’, simple visuals (weekday counts, credits histogram, schedule heatmap), and an **HTML demo deck** export.”*

**Why it mattered**  
Delivers the actual student-friendly experience and gives you a portable artifact to share.

**Implementation Outcomes**  
- `transformers.py`:  
  - **Search** filters with day/time overlap logic; grouped expanders; “DOC link”.  
  - **Visuals**: bar chart, histogram, heatmap.  
  - **Export**: CSV and `build_html_deck()` → `docs/demo_deck.html` (one file, offline).

**Files touched**  
- `src/transformers.py`

---

## 10) CLI & Flag Hygiene

**Prompt**  
*“Fix CLI issues: hyphenated flags should map to underscore attrs; add `-o/--out` for output path.”*

**Why it mattered**  
Avoids runtime errors and makes CLI demonstrations smooth.

**Implementation Outcomes**  
- `argparse`: `-o/--out` added; access `args.discover_subjects` (underscore); cleaned help text.

**Files touched**  
- `src/scraper.py` (main/CLI)

---

## 11) Subjects for Clean Demo

**Prompt**  
*“Recommend a short, reliable subject set so everything looks clean for grading.”*

**Outcome**  
- Use **COMS**, **STAT**, **APMA** (MATH/ECON usually fine).  
- Demo Mode pre-selects COMS/STAT.

**Files touched**  
- `src/transformers.py` (demo defaults)

---

## 12) Submission Hygiene

**Prompt**  
*“Keep grader-required files only; remove dev/test artifacts; enforce with `.gitignore`.”*

**Why it mattered**  
Prevents automated grading failures due to extra files/dirs.

**Implementation Outcomes**  
- Keep: `src/{scraper,validators,transformers}.py`, `docs/{ARCHITECTURE,AI_USAGE,BUSINESS_CASE,ETHICS}.md`, `data/sample_output.json`, `README.md`, `requirements.txt`, `.gitignore`.  
- Ignore/remove: `src/__pycache__`, `tests/`, `venv/`, extra data JSON/CSV, `docs/*.html` (export deck), tmp scripts.

---

# Re-usable Master Prompts (Copy/Paste)

### A) Discovery (authoritative)
> **Discover subjects only from Columbia’s A–Z term index.** Normalize “Fall 2025” → `Fall2025`. Keep anchors whose **TEXT equals** that string (no guessing). Extract subject code from `/subj/{CODE}/_{term}.html`. Return `{code, name}` from the parent line before term tokens.

### B) Parsing (plain-text, header-slices)
> **Use the plain-text listing** reachable from `/subj/{SUBJ}/_{TERM}.html` (“plain text version”). Build **column slices** from the header row for `Number/Sec/Call#/Pts/Title/Day/Time/Room/Building/Faculty`. Parse rows strictly by slices.

### C) Row Guard
> Emit a course **only** if `title` is non-empty **and** `(number || section || numeric Call#)` is present. Drop banners/continuations.

### D) Instructor Continuation
> If the prior row’s instructor ends with a comma, and the current “Faculty” has text, **append** it to complete the name.

### E) Time Parsing (priority + fallback)
> **Priority order**: AM/PM range → 24h range → HHMM digits → single time → TBA.  
> **Accept full-line only if the range increases**; otherwise use the **Time** column slice.  
> If the line mentions `pm` (not `am`), **coerce `<12:00` to afternoon** to avoid morning ghosts. Duplicate single times to both start/end.

### F) Days
> Map compact tokens to `["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]`. Example: `MWF` → `Mon,Wed,Fri`; `TuTh` → `Tue,Thu`.

### G) Location Repair
> Join `room='To be'` + `building contains 'announced'` ⇒ `building='To be announced'`, `room=None`.  
> If `room` ends with a single uppercase letter and `building` starts lowercase, move the letter to building head (e.g., “Kravis”), trim room.

### H) Recitation Linking
> Flag recitations (`R##` or `RECITATION` + 0 credits). Build `detail_url` and parse parent lecture via “Required recitation … enrolled in ({SUBJ}) ({NUMBER})”. Fallback: title-normalized match within subject.

### I) UI & Export
> **Streamlit UI** with filters (credits, days, optional time window, keyword), grouped course view with **DOC link**. Visuals: weekday counts (primaries), credits histogram, schedule heatmap. Export CSV and a one-file **HTML deck**.

### J) CLI Flags
> Add `-o/--out` and ensure hyphenated `--discover-subjects` maps to `args.discover_subjects` in code.

---

# Acceptance Checklist (Quick)

- [ ] Days appear as full names.  
- [ ] Times are `HH:MM` 24h or `None`; **no** 00:10/00:55 ghosts on PM lines.  
- [ ] Location “To be announced” has `room=None`; Kravis/Diana letter fix applied.  
- [ ] Banners not emitted; recitations linked when disclosed.  
- [ ] “DOC link” opens detail page.  
- [ ] Streamlit filters work; Visuals render; HTML deck exports.
