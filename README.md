# Lab2DataIsGold

## Project Structure

```
project-name/
├── src/
│   ├── scraper.py          # Main scraping logic
│   ├── validators.py       # Data validation rules
│   ├── transformers.py     # Data transformation pipeline
├── docs/
│   ├── BUSINESS_CASE.md    # Market analysis and pricing
│   ├── ETHICS.md           # Detailed ethical analysis
│   ├── ARCHITECTURE.md     # Technical design decisions
│   ├── AI_USAGE.md         # AI collaboration documentation
├── data/
│   └── sample_output.json  # Example of processed data
├── requirements.txt
├── README.md
└── .gitignore
```

# Columbia Course Finder (Demo)

> **🎯 SUBMISSION INFO - PLEASE GRADE THIS BRANCH 🎯**  
> **Graded branch**: `submission-files` ⭐ **THIS IS THE BRANCH TO GRADE** ⭐  
> **Submission date**: September 16, 2025  
> **Final submission commit**: Latest commit on `submission-files` branch  

> ⚠️ **IMPORTANT FOR GRADERS**: This `submission-files` branch contains the final, complete submission. Please use this branch for grading, not `main` or any other branch.

> This repository structure matches all assignment requirements. All documentation, source code, and deliverables are included and ready for evaluation.

A student-friendly search over Columbia’s Directory of Classes (DOC):

- **Discover** official subjects for a term (A–Z index, no guessing)  
- **Scrape** the subject’s **plain-text** listing (stable columns)  
- **Parse & normalize** days/times/locations/instructors  
- **Link** recitations to parent lectures when disclosed  
- **Filter & visualize** in Streamlit; **export** CSV and an offline **HTML deck**

## Quick Start

```bash
pip install -r requirements.txt

# Streamlit UI
streamlit run src/transformers.py
Demo flow: Term “Fall 2025” → select COMS, STAT, APMA → Scrape now → Search filters (e.g., Tue/Thu) → Visuals → Export deck.

CLI
bash
Copy code
python -m src.scraper --scrape --term "Fall 2025" --subjects COMS STAT APMA -o data/sample_output.json
Architecture (1-slide)
mermaid
Copy code
flowchart LR
  UI[Streamlit] -->|discover_subjects_for_term| S[scraper.py]
  S --> AZ[(A–Z term index)]
  UI -->|scrape_many| S
  S --> SUBJ[(subject term page)]
  S --> TEXT[(plain-text listing)]
  S --> PARSE[parser]
  PARSE --> LINK[link recitations]
  LINK --> DETAIL[(section detail)]
  LINK --> UI
  UI --> OUT[(table, charts, HTML deck, CSV/JSON)]
Files
src/scraper.py — discovery, fetching, parsing, recitation linking

src/validators.py — dataclass normalization + flatten for UI

src/transformers.py — Streamlit UI, charts, export

data/sample_output.json — example output

docs/ — ARCHITECTURE, AI_USAGE, ETHICS, BUSINESS_CASE

Notes
Scrapes only public DOC pages; throttled and retried politely.

Recommended demo subjects: COMS, STAT, APMA.