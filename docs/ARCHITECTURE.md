# Technical design decisions

## Design Goals & Constraints

- **Authoritative discovery** — only subjects listed on Columbia’s A–Z term index.
- **Stable source** — parse the **plain-text** listing (not the dynamic JS pages).
- **Deterministic parsing** — build column slices from header offsets (not ad-hoc regex).
- **User-oriented search** — filter by day, time window, credits, keyword; expand courses with DOC links.
- **Demo-friendly** — fast, clean subjects (**COMS**, **STAT**, **APMA**) for baseline.

---

## Test-Driven Acceptance (guided the build)

**User story**

> _“Find all **2-credit** classes on **Monday around 4:30 PM**; show **instructor**, **title**, **location**, **start/end times**, and a **link** back to DOC.”_

**Acceptance checks**

- **Filters**  
  Credits interval works for fixed/variable credits; day picker uses canonical `["Mon", "Tue", ...]`; time overlap rule: `(end > filter_start) ∧ (start < filter_end)`.

- **Data correctness**  
  Days are full names (not `TuTh`); times are `HH:MM` 24h or `None` (TBA); **no `00:10/00:55` ghosts** on PM lines; `"To be announced"` implies `room=None`; instructor continuation merges tails; row guard blocks department banners.

- **Linkage**  
  Recitations (`R##` or 0-credit) get `parent_course_code` when disclosed; every row has a DOC detail link.

- **UX**  
  Scraping **COMS/STAT/APMA** completes in seconds; visuals render; export produces a one-file HTML deck.

---

## High-Level Flow

flowchart LR
  U[User] -->|Term + Subjects| UI[Streamlit (transformers.py)]
  UI -->|discover_subjects_for_term| S[scraper.py]
  S -->|GET sel/subj-A..Z| AZ[(DOC A–Z term pages)]
  UI -->|scrape_many| S
  S -->|GET subj/{SUBJ}/_{TERM}.html| SUBJ[(DOC subject term page)]
  S -->|follow 'plain text version'| TEXT[(DOC plain text listing)]
  S -->|parse_subject_text_page| PARSE[Row parser]
  PARSE -->|section dicts| LINK[link_recitations]
  LINK -->|maybe GET detail| DETAIL[(DOC section detail)]
  LINK -->|linked sections| UI
  UI -->|normalize_sections| VAL[validators.py]
  VAL -->|flatten_for_display| UI
  UI -->|Search/Charts/Export| OUT[(Table, Charts, HTML deck, CSV/JSON)]



# Key Components

## `src/scraper.py`

### Discovery — `discover_subjects_for_term(term, session)`
- Crawl: `https://doc.sis.columbia.edu/sel/subj-{A..Z}.html`
- Normalize term (e.g., `Fall 2025 → Fall2025`)
- Keep anchors whose text equals the term
- Extract `{CODE}` from `/subj/{CODE}/_{term}.html`

### Fetch
- `GET /subj/{SUBJ}/_{TERM}.html`
- Follow the plain-text listing (fallback to `_{TERM}_text.html`)
- Polite throttle + `tenacity` retry

### Parse — `parse_subject_text_page(text_html, subject, term_label)`
- Detect header containing **Number**, **Call#**, **Faculty**
- Build deterministic column slices from header label offsets

**Row guard**  
- `_is_real_course_row`: must have title + (number OR section OR numeric Call#)

**Instructor continuation**  
- If previous instructor ends with a comma, append current Faculty

**Time parsing — `parse_timerange_any`**
- Normalize unicode dashes & “to”
- Try AM/PM range → 24h range → HHMM digits → single time → TBA
- Prefer **full-line** only when it yields an increasing range; else fallback to **Time** column
- **PM-only coercion** converts `<12:00` to afternoon when line contains `pm` but not `am`

**Days**
- Map `M/T/W/R/F/S/U` → full names

**Location — `_repair_location`**
- Join “To be” + “announced” → `"To be announced"`, set `room=None`
- Move trailing room letter to building when building starts lowercase  
  (e.g., `"620 K" + "ravis Hall"` → `"620", "Kravis Hall"`)

**Credits**
- Fixed or range

### Recitations — `link_recitations(sections, term_code, session)`
- Flag recitations (`R##` / 0-credit)
- Fetch detail page and match `Required recitation … enrolled in ({SUBJ}) ({NUMBER})`
- Else fallback to title match

### CLI usage
```bash
python -m src.scraper --scrape --term "Fall 2025" --subjects COMS STAT APMA -o data/sample_output.json



