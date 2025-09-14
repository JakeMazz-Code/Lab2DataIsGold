# src/scraper.py
from __future__ import annotations
import argparse, re, time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dateutil import parser as dtparser

from validators import Course, Section, Meeting, Location, write_json, _split_compact_days

BASE = "https://doc.sis.columbia.edu"
UA = {"User-Agent": "ColumbiaCoursePOC/1.1 (+educational demo)"}

# ------------------- HTTP utils -------------------

def polite_get(session: requests.Session, url: str, throttle: float = 1.0) -> requests.Response:
    time.sleep(max(throttle, 0.0))
    resp = session.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    return resp

@retry(reraise=True, wait=wait_exponential(multiplier=1, min=1, max=8),
       stop=stop_after_attempt(3), retry=retry_if_exception_type((requests.RequestException,)))
def fetch_text(session: requests.Session, url: str, throttle: float = 1.0) -> str:
    return polite_get(session, url, throttle).text

def robots_allows(session: requests.Session, host_base: str, path: str) -> bool:
    try:
        r = session.get(urljoin(host_base, "/robots.txt"), headers=UA, timeout=15)
        if r.status_code != 200:
            return True
        disallows = []
        ua_all = False
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if line.lower().startswith("user-agent"):
                ua_all = "*" in line
            if ua_all and line.lower().startswith("disallow:"):
                disallows.append(line.split(":")[1].strip())
        for rule in disallows:
            if not rule: return True
            if path.startswith(rule): return False
        return True
    except Exception:
        return True

# ------------------- Parsing helpers -------------------

def _to_24h(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    s = s.strip()
    if not s or s.upper() in {"TBA", "ARR"}: return None
    s = s.replace("Noon", "12:00 PM").replace("noon", "12:00 PM")
    s = s.replace("Midnight", "12:00 AM").replace("midnight", "12:00 AM")
    try:
        t = dtparser.parse(s, fuzzy=True); return t.strftime("%H:%M")
    except Exception:
        if s.endswith("a") or s.endswith("p"):
            try:
                t = dtparser.parse(s + "m", fuzzy=True); return t.strftime("%H:%M")
            except Exception:
                return None
        return None

def _days_compact_to_tokens(s: str) -> List[str]:
    """
    Columbia text pages use compact letters: M T W R F S U; TR means Tue+Thu.
    Reuse validators splitter for Tu/Th; handle single letters explicitly.
    """
    s = (s or "").strip().upper()
    if not s: return []
    # Quickly map single letters to canonical tokens
    mapping = {"M":"M", "T":"Tu", "W":"W", "R":"Th", "F":"F", "S":"Sa", "U":"Su"}
    out: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]; nxt = s[i+1] if i+1 < len(s) else ""
        if ch == "T" and nxt == "H":
            out.append("Th"); i += 2; continue
        if ch == "T" and nxt == "U":
            out.append("Tu"); i += 2; continue
        out.append(mapping.get(ch, None) or "")
        i += 1
    # cleanup
    out = [x for x in out if x]
    # dedupe preserve order
    seen=set(); dedup=[]
    for d in out:
        if d not in seen:
            seen.add(d); dedup.append(d)
    return dedup

# ------------------- Columbia DOC Scraper -------------------

class ColumbiaDOCScraper:
    """
    Scrapes Columbia Directory of Classes using STATIC endpoints:
      - Subject HTML: /subj/{SUBJ}/_{TERM}.html  (maps section detail URLs)
      - Subject TEXT: /subj/{SUBJ}/_{TERM}_text.html  (reliable section rows)
    Optional Selenium flow is available to drive Angular pages and hop to the
    same text endpoint if needed.
    """

    def __init__(self, term_label: str, subjects: List[str], throttle: float = 1.0,
                 enrich_descriptions: bool = True, use_selenium: bool = False):
        self.term_label = self._normalize_term(term_label)      # "Fall2025"
        self.subjects = [s.strip().upper() for s in subjects if s.strip()]
        self.throttle = throttle
        self.enrich_descriptions = enrich_descriptions
        self.use_selenium = use_selenium
        self.session = requests.Session()

    @staticmethod
    def _normalize_term(term_label: str) -> str:
        s = term_label.replace(" ", "")
        assert re.match(r"^(Fall|Spring|Summer)\d{4}$", s), f"Bad term: {term_label}"
        return s

    @staticmethod
    def _term_human(term_label: str) -> str:
        return f"{term_label[:-4]} {term_label[-4:]}"

    def _subj_html_url(self, subject: str) -> str:
        return f"{BASE}/subj/{subject}/_{self.term_label}.html"

    def _subj_text_url(self, subject: str) -> str:
        return f"{BASE}/subj/{subject}/_{self.term_label}_text.html"

    def _map_section_links(self, html: str, subject: str) -> Dict[Tuple[str, str], str]:
        soup = BeautifulSoup(html, "lxml")
        mapping: Dict[Tuple[str, str], str] = {}
        anchors = soup.find_all("a")
        # examples: /subj/MECE/E3100-20243-001/
        href_pat = re.compile(rf"/subj/{re.escape(subject)}/([A-Z]{{1,3}}\d{{3,4}})-(\d+)-([A-Za-z0-9]+)/")
        for a in anchors:
            href = a.get("href") or ""
            m = href_pat.search(href)
            if m:
                number, section = m.group(1), m.group(3)
                mapping[(number, section)] = urljoin(BASE, href)
        return mapping

    def _fetch_section_description(self, url: str) -> Optional[str]:
        html = fetch_text(self.session, url, throttle=self.throttle)
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text("\n", strip=True)
        m = re.search(r"Course Description\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if not m: return None
        desc = m.group(1).strip()
        desc = re.split(r"(Web Site|Department|Enrollment|Subject|Number|Section|Division|Method of Instruction|Type)\s*\|",
                        desc, maxsplit=1)[0]
        desc = re.sub(r"\s+", " ", desc).strip()
        return desc[:1000] if desc else None

    def _parse_subject_text(self, text: str, subject: str) -> List[Dict[str, Any]]:
        """
        Parse the plain-text listing into records:
        Columns: Number Sec Call# Pts Title Day Time Room Building Faculty
        Handle times like '10:10am-11:25' or '4:10pm-6:40pm' or '11:00a-11:50a'
        """
        rows: List[Dict[str, Any]] = []
        pat = re.compile(
            r"^\s*(?P<number>[A-Z]{1,3}\d{3,4})\s+"
            r"(?P<section>[A-Za-z0-9]{1,3})\s+"
            r"(?P<call>\d{3,6})\s+"
            r"(?P<pts>\d+(?:\.\d+)?)\s+"
            r"(?P<title>.+?)\s{2,}"
            r"(?P<days>[MTWRFSU]{1,7})\s+"
            r"(?P<start>\d{1,2}:\d{2}(?:\s*[ap]m?)?)"
            r"(?:\s*-\s*(?P<end>\d{1,2}:\d{2}(?:\s*[ap]m?)?))?"
            r"\s+(?P<room_building>.+?)\s{2,}"
            r"(?P<faculty>.+?)\s*$"
        )
        for line in text.splitlines():
            if not line or "Number Sec  Call#" in line:  # header
                continue
            m = pat.match(line)
            if not m:
                continue
            gd = m.groupdict()
            rows.append({
                "subject": subject,
                "number": gd["number"],
                "section": gd["section"],
                "crn": gd["call"],
                "points": gd["pts"],
                "title": re.sub(r"\s+", " ", gd["title"]).strip(),
                "days_tokens": _days_compact_to_tokens(gd["days"]),
                "start_24": _to_24h(gd["start"]),
                "end_24": _to_24h(gd.get("end")),
                "room_building": re.sub(r"\s+", " ", gd["room_building"]).strip(),
                "instructor": re.sub(r"\s+", " ", gd["faculty"]).strip(),
            })
        return rows

    # -------------- Public entry --------------

    def scrape_subject(self, subject: str) -> List[Course]:
        html = fetch_text(self.session, self._subj_html_url(subject), throttle=self.throttle)
        text = fetch_text(self.session, self._subj_text_url(subject), throttle=self.throttle)

        link_map = self._map_section_links(html, subject)
        raw_rows = self._parse_subject_text(text, subject)

        courses_by_key: Dict[Tuple[str, str], Course] = {}
        for r in raw_rows:
            key = (subject, r["number"])
            course = courses_by_key.get(key)
            if not course:
                course = Course(
                    university="Columbia University",
                    subject=subject,
                    number=r["number"],
                    course_code=f"{subject} {r['number']}",
                    title=r["title"],
                    credits=r["points"],
                    description=None,
                    prerequisites=None,
                    sections=[],
                )
                courses_by_key[key] = course

            # location split
            building = room = None
            tokens = r["room_building"].split()
            if tokens and re.match(r"^\d+[A-Z]?$", tokens[0]):  # e.g., 417, 451, 301M
                room = tokens[0]
                building = " ".join(tokens[1:]) if len(tokens) > 1 else None
            else:
                building = r["room_building"]

            mtg = Meeting(
                days=r["days_tokens"],
                start_time=r["start_24"],
                end_time=r["end_24"],
                time_tba=False if (r["start_24"] or r["end_24"]) else True,
                location=Location(building=building, room=room),
            )
            sec = Section(
                term=self._term_human(self.term_label),
                crn=r["crn"],
                section=r["section"],
                instructor=r["instructor"],
                status=None,
                meetings=[mtg],
            )
            course.sections.append(sec)

            # Optional description enrichment (first time we see this course)
            if self.enrich_descriptions and not course.description:
                detail_url = link_map.get((r["number"], r["section"]))
                if detail_url:
                    try:
                        desc = self._fetch_section_description(detail_url)
                        if desc: course.description = desc
                    except Exception:
                        pass

        return list(courses_by_key.values())

    # -------------- Selenium fallback (optional) --------------

    def scrape_subject_with_selenium(self, subject: str) -> List[Course]:
        """
        Opens the Angular route then clicks 'plain text version' to reuse the same parser.
        """
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(options=options)
        try:
            url = f"{BASE}/#sel/{subject}_{self.term_label}.html"
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "plain text")))
            # Click 'plain text version'
            driver.find_element(By.PARTIAL_LINK_TEXT, "plain text").click()
            WebDriverWait(driver, 20).until(EC.title_contains("Subject Listing"))
            text_html = driver.page_source
        finally:
            driver.quit()

        # parse with BS4 and reuse text parser
        soup = BeautifulSoup(text_html, "lxml")
        body_txt = soup.get_text("\n", strip=False)
        return self._rows_to_courses(self._parse_subject_text(body_txt, subject), subject)

    # helper for selenium path
    def _rows_to_courses(self, raw_rows: List[Dict[str, Any]], subject: str) -> List[Course]:
        courses_by_key: Dict[Tuple[str, str], Course] = {}
        for r in raw_rows:
            key = (subject, r["number"])
            if key not in courses_by_key:
                courses_by_key[key] = Course(
                    university="Columbia University",
                    subject=subject, number=r["number"],
                    course_code=f"{subject} {r['number']}",
                    title=r["title"], credits=r["points"], sections=[]
                )
            course = courses_by_key[key]
            tokens = r["room_building"].split()
            building = " ".join(tokens[1:]) if tokens and re.match(r"^\d+[A-Z]?$", tokens[0]) else r["room_building"]
            room = tokens[0] if tokens and re.match(r"^\d+[A-Z]?$", tokens[0]) else None
            mtg = Meeting(days=r["days_tokens"], start_time=r["start_24"], end_time=r["end_24"],
                          time_tba=False if (r["start_24"] or r["end_24"]) else True,
                          location=Location(building=building, room=room))
            course.sections.append(Section(term=self._term_human(self.term_label),
                                           crn=r["crn"], section=r["section"], instructor=r["instructor"],
                                           meetings=[mtg]))
        return list(courses_by_key.values())

    # -------------- Run all subjects --------------

    def scrape(self) -> List[Course]:
        if not robots_allows(self.session, BASE, "/"):
            raise RuntimeError("robots.txt disallows scraping this path.")

        all_courses: List[Course] = []
        for subj in self.subjects:
            if self.use_selenium:
                courses = self.scrape_subject_with_selenium(subj)
            else:
                courses = self.scrape_subject(subj)
            all_courses.extend(courses)
        return all_courses

# ------------------- CLI -------------------

def main():
    ap = argparse.ArgumentParser(description="Scrape Columbia DOC by subject and term.")
    ap.add_argument("--term", required=True, help='e.g., "Fall2025" or "Fall 2025"')
    ap.add_argument("--subjects", required=True, help="Comma-separated subject codes, e.g., COMS,STAT,ECON")
    ap.add_argument("--out", default="data/sample_output.json")
    ap.add_argument("--throttle", type=float, default=1.0)
    ap.add_argument("--no-desc", action="store_true", help="Skip per-section description enrichment")
    ap.add_argument("--selenium", action="store_true", help="Use Selenium fallback (Angular route)")
    args = ap.parse_args()

    subjects = [s.strip() for s in args.subjects.split(",") if s.strip()]
    scraper = ColumbiaDOCScraper(
        term_label=args.term, subjects=subjects, throttle=args.throttle,
        enrich_descriptions=not args.no_desc, use_selenium=args.selenium
    )
    courses = scraper.scrape()
    write_json(args.out, courses)
    print(f"Wrote {len(courses)} courses to {args.out}")

if __name__ == "__main__":
    main()
