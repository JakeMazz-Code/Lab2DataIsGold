# AI collaboration documentation

# Purpose

Record how AI assistance was used, how prompts shaped design, and how our initial **test-driven acceptance** steered implementation toward stable behavior.

---

## Collaboration Model

- **You** (PM/Eng): specified constraints (“no dynamic JS scraping”), acceptance tests (“find 2-credit classes Monday ~4:30 PM”), and demo ergonomics.
- **AI** (assistant): drafted parsing & UI scaffolding, then iterated under acceptance to harden time/day/location handling.

This was **prompt → run → observe → refactor**; not a code dump.

---

## Initial Test-Driven Acceptance (North Star)

> _“In the dashboard I can filter to **2 credits**, **Monday** around **4:30 PM**, and see **instructor/title/location/start-end** plus a **DOC link**.”_

**Implications we enforced**

- Times must be 24h `HH:MM` (or `None` for TBA); **no `00:10/00:55` ghosts** on PM lines.
- Day compacts ⇒ canonical lists (`["Tue","Thu"]`, `["Mon","Wed","Fri"]`).
- Location `"To be announced"` ⇒ `room=None`; Kravis/Diana letter fix.
- Banners never emitted; recitations linked where disclosed.
- Visuals and export must work on **COMS/STAT/APMA** in seconds.

---

## Prompt Trace (abridged)

**Authority + Source**  
- _Prompt_: “Only scrape official subjects from A–Z; no guessing codes.”  
- _Outcome_: `discover_subjects_for_term` keeps anchors whose **text equals** normalized term (`Fall2025`).

**Stable Parsing**  
- _Prompt_: “Use the **plain-text version**; derive column slices from header offsets.”  
- _Outcome_: `_detect_columns` and deterministic slicing.

**Time Handling**  
- _Prompt_: “Support `1:10 PM–2:25 PM`, `1410-1525`, `13:10 to 14:25`, and **single times**; duplicate singles; fix morning ghosts on PM lines.”  
- _Outcome_: `parse_timerange_any` with **full-line increasing range** priority; fallback to **Time** slice; PM-only coercion.

**Row Guard + Continuations**  
- _Prompt_: “Do not emit department banners; merge Faculty continuation when prior instructor ends with comma.”  
- _Outcome_: `_is_real_course_row` + continuation merge.

**Location Repair**  
- _Prompt_: “Join `To be` + `announced`; fix off-by-one building letter (‘Kravis/Diana’).”  
- _Outcome_: `_repair_location`.

**Demo Ergonomics**  
- _Prompt_: “Make it easy to present (filters, visuals, one-file deck).”  
- _Outcome_: Export **HTML deck**; **COMS/STAT/APMA** suggested as clean defaults.

---

## AI-Generated vs Human-Curated

| Area | Status |
|---|---|
| Time parsing (`parse_timerange_any`, `parse_time_label`) | AI draft, human ordering & safety (range must increase; slice fallback; PM coercion) |
| Row guard & instructor continuation | AI idea, human acceptance & integration |
| Location repair (`_repair_location`) | AI suggestion, human examples & guardrails |
| Recitation linking | Human design (detail-page regex + fallback) |
| Streamlit UI & export | AI scaffold, human polish & stability |
| Subject discovery | Human insistence on authoritative anchors only |

---

## Bugs Found in AI Suggestions & Fixes

1. **Over-matching full-line times** captured incidental numbers.  
   **Fix**: accept full-line **only** when range is increasing; else use **Time** slice.

2. **One-sided AM/PM** mis-labeled ranges.  
   **Fix**: propagate meridiem from the side that has it.

3. **Morning ghosts** on PM lines (`00:10`, `00:55`).  
   **Fix**: PM-only coercion.

4. **Banners emitted as courses**.  
   **Fix**: row guard requires title + (number **or** section **or** numeric Call#).

5. **Split TBA & Kravis/Diana letter**.  
   **Fix**: location repair joining TBA and moving trailing letter when building starts lowercase.

6. **UI showed blanks while JSON had times** (mixed labels).  
   **Fix**: Streamlit displays normalized `HH:MM` only (or omitted).

---

## Performance Notes

- **Subjects for clean demo**: **COMS, STAT, APMA** (MATH/ECON also typically clean).
- **Streamlit Cache**: discovery (1 h), scrapes (5 min).
- **Network**: polite 350–400 ms throttle; `tenacity` retry.

---

## Verification

- Manual UI checks: days in canonical order, times normalized, TBA respected, recitations linked, visuals render.
- CLI sanity:
  ```bash