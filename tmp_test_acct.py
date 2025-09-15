import sys
import json
import requests

# Allow importing from src/
sys.path.append("src")
from scraper import scrape_many  # type: ignore

def main():
    term = "Fall2025"
    subjects = ["ACCT"]
    session = requests.Session()
    sections = scrape_many(subjects, term, session)
    print(f"Scraped {len(sections)} sections for {subjects[0]} {term}")
    for s in sections[:8]:
        print(s.get("course_code"), s.get("days"), s.get("start_time"), s.get("end_time"))
    with open("data/acct.json", "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    print("[ok] wrote data/acct.json")

if __name__ == "__main__":
    main()


