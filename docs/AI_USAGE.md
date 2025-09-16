# AI collaboration documentation

AI USAGE
Scope & Intent

This document explains how AI was used (and bounded) to build a robust, scrape-friendly course finder:

We constrained AI to stable sources (Columbia DOC plain-text pages).

We drove development via test-driven acceptance (“find 2-credit, Mon ~4:30 PM, show instructor/title/location/times + DOC link”).

We used AI for drafting parsing logic and UI scaffolding, then hardened it with human guardrails and real outputs.

Style: prompt → run → observe → refactor. Every AI suggestion had to pass the acceptance behavior in the Streamlit UI and CLI outputs.

Collaboration Timeline (high-level)

Milestone 1 — Problem framing & constraints

No dynamic JS scraping (Angular) — plain-text listing only.

Authoritative subjects via A–Z anchors (no guesses).

UI must filter by days, time window, credits, keyword.

Milestone 2 — Baseline parsing & UI

AI drafted header-slice parser & Streamlit table.

Human added row guard to block department banners; normalized location formatting.

Milestone 3 — Time parsing reliability

AI created multi-format time parser (AM/PM, 24h, HHMM).

Human enforced: full-line range only if increasing; else fallback to Time column; added PM-only coercion (fix 00:10/00:55 ghosts).

Milestone 4 — Linking recitations

AI proposed R## detection; human built detail-page regex + title fallback.

Milestone 5 — Demo polish

Streamlit charts, HTML demo deck export.

Optional separate storyboard dashboard for “what’s happening” (kept out of submission).

Initial Test-Driven Acceptance (North Star)

“In the dashboard I can filter to 2 credits, Monday around 4:30 PM, and see instructor, title, location, start/end, and a DOC link.”

Derived acceptance checks

Days: canonical ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] (no raw MW/TuTh).

Times: 24h "HH:MM" or None (TBA) — no 00:10/00:55 ghosts on PM lines.

Overlap rule: (end > filter_start) ∧ (start < filter_end).

Location: "To be announced" ⇒ room=None; letter-shift fix (e.g., "620 K" + "ravis Hall" → "620", "Kravis Hall").

Row guard: banners/continuations not emitted.

Recitations: flagged; parent_course_code set when disclosed.

Provenance: row includes DOC detail URL.

Prompt Catalogue (abridged, the ones that moved the needle)

Authority & stability

Prompt: “Discover subjects only from A–Z term index; keep anchors whose TEXT equals normalized term (Fall2025). Don’t guess codes.”

Change: Implemented discover_subjects_for_term() with term normalization and anchor-text equality; extracted {CODE} only from /subj/{CODE}/_{term}.html.

Plain-text parsing by header slices

Prompt: “Use the ‘plain text version’. Build fixed column slices by measuring header label offsets (stable across spacing).”

Change: _detect_columns() computes slices for Number/Sec/Call#/Pts/Title/Day/Time/Room/Building/Faculty.

Row guard

Prompt: “Do not emit department banners like ‘L App Activ / RECIT’. Emit only if title and (number || section || numeric Call#).”

Change: _is_real_course_row().

Instructor continuation

Prompt: “If previous instructor ends with a comma, append the current Faculty tail.”

Change: Continuation merge logic added after slicing.

Time parsing (full-line first, safe fallback)

Prompt: “Support 1:10 PM–2:25 PM, 1410-1525, 13:10 to 14:25, and single times (duplicate). Accept full-line only if increasing range; otherwise fallback to Time slice. Handle ‘pm only’ lines to avoid morning ghosts.”

Change: parse_timerange_any() with:

unicode dash/to normalization,

order: AM/PM range → 24h range → HHMM digits → single → TBA,

range must increase,

fallback to Time column when full-line unsafe,

_coerce_pm_if_needed() for PM-only lines.

Location repair

Prompt: “Join ‘To be’ + ‘announced’. If room ends with a single uppercase letter and building starts lowercase (e.g., ‘620 K’ + ‘ravis Hall’), move letter to building (‘Kravis Hall’).”

Change: _repair_location() applies both fixes; "To be announced" forces room=None.

Recitations linking

Prompt: “Flag R##/0-credit recitations; parse parent from detail page if ‘Required recitation… enrolled in {SUBJ} {NUMBER}’; fallback to title match.”

Change: link_recitations() with detail-page regex + fallback.

Demo ergonomics

Prompt: “Make it easy to present (filters, visuals, one-file HTML deck).”

Change: Streamlit charts + build_html_deck() export.

AI vs Human Ownership Matrix
Area	AI Draft	Human Final
Subject discovery (A–Z anchors)	✅	✅ anchored to text equality, no guessing
Header slices & core parse	✅	✅ enforced row guard & continuation
Time parsing (multi-format)	✅	✅ full-line must increase, Time slice fallback, PM coercion
Location repair	✅	✅ TBA join + letter shift with safety guards
Recitation linking	⚪	✅ detail regex + robust fallback
Streamlit UI & charts	✅	✅ display rules, filters, deck content
Submission hygiene (.gitignore, structure)	⚪	✅
Failure Case Gallery (and fixes)

Full-line over-match grabbed collateral digits (e.g., room numbers)
Fix: accept full-line only when range increases; otherwise parse Time column slice.

One-sided AM/PM produced wrong meridiem
Fix: propagate meridiem from whichever side has it.

PM-only “morning ghosts” (00:10, 00:55)
Fix: _coerce_pm_if_needed() when line contains pm but not am.

Banners as course rows
Fix: _is_real_course_row() requires title and (number || section || numeric Call#).

Split TBA & Kravis/Diana letter drift
Fix: _repair_location() joins TBA and shifts trailing letter from room to building when building starts lowercase.

UI blanks despite valid JSON
Fix: Streamlit displays normalized "HH:MM" consistently; no mixed labels; TBA left None.

Quality Gates & Checks

Manual acceptance via Streamlit (COMS/STAT/APMA):

Days render as Mon, Tue, ... strings; times show "HH:MM", no ghosts.

“DOC link” resolves to detail pages.

Visuals render for primaries; heatmap looks sane.

CLI sanity:

python -m src.scraper --scrape --term "Fall 2025" --subjects COMS STAT APMA -o data/sample_output.json


Check: significant section count; no banner rows; times/locations populated as expected.

Performance:

polite ~350–400 ms throttle; tenacity backoff.

Streamlit caches: discovery (1 h), scrapes (5 min).

Concrete Prompt → Code Examples

Time parsing order & fallback

Prompt: “Accept full-line ranges only if increasing; else fallback to Time column. Support AM/PM, 24h, HHMM; duplicate single bounds; coerce PM-only lines.”
Change: parse_timerange_any()
  1) AM/PM range (propagate meridiem) → validate end > start
  2) 24h range → validate end > start
  3) HHMM digit range → validate end > start
  4) Single time (any format) → duplicate bounds
  5) TBA
Fallback: If full-line fails, parse slices['Time'].
Coercion: If line has “pm” but not “am”, bump < 12:00 to afternoon.


Row guard

Prompt: “Do not emit department banners. Require title and (number || section || numeric Call#).”
Change: _is_real_course_row()


Location repair

Prompt: “If room='To be' and building contains 'announced' ⇒ 'To be announced', room=None.
If room ends with one uppercase letter and building starts lowercase ⇒ move letter to building head.”
Change: _repair_location()

Ethics & Constraints (AI & Ops)

Data source: only public DOC pages; no logins or PII.

Load: throttled & retried; Streamlit cache reduces repeated hits.

Transparency: each row links back to official DOC.

Submission hygiene: demo helpers (bts_demo.py, exports) excluded per grading contract.

(See docs/ETHICS.md for legal context & citations.)

Maintenance with AI — Do / Don’t

Do

Keep prompts constrained to stable sources & acceptance tests.

Require deterministic outcomes (header slices, explicit fallbacks).

Re-run the acceptance behavior (Streamlit filters + CLI) after changes.

Don’t

Let AI infer subject lists (must use A–Z anchors).

Parse dynamic JS UIs when a plain-text listing exists.

Accept full-line times without increasing range validation.

Repro & Run

Streamlit

streamlit run src/transformers.py


CLI

python -m src.scraper --scrape --term "Fall 2025" --subjects COMS STAT APMA -o data/sample_output.json


Export
Use the Export tab to generate a one-file HTML demo deck (docs/demo_deck.html).

Lessons Learned

Plain-text + header-slice parsing is far more robust than DOM scraping dynamic pages.

The acceptance test (Mon ~4:30 PM, 2 credits) directly revealed the need for PM coercion and strict range validation.

Small, surgical heuristics (row guard, continuation merge, location repair) eliminate most real-world grit.

A separate storyboard window is the safest way to communicate “behind-the-scenes” without perturbing the main app.