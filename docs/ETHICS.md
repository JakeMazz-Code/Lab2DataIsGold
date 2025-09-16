# Detailed Ethical Analysis

## 1. Legal Analysis

### Copyright & Database Law
- U.S. copyright law (**17 U.S.C. § 102**) does not protect facts such as course names, times, or instructors.
- The arrangement of data may be protectable, but extracting factual course information and re-structuring it in a new dataset does not infringe.

### Computer Fraud and Abuse Act (CFAA, **18 U.S.C. § 1030**)
- CFAA prohibits unauthorized access to protected systems.
- *HiQ Labs, Inc. v. LinkedIn Corp.* (9th Cir. 2019, 2022): The Ninth Circuit held that scraping publicly available data (no login, no password protection) does not constitute “unauthorized access” under CFAA. This ruling, let stand by the Supreme Court in 2022, is widely seen as affirming the legality of scraping public websites.
- Columbia’s Directory of Classes is a public-facing site, not behind authentication, making it similar to the “public LinkedIn profiles” at issue in *HiQ*.

### Other Relevant Precedents
- *Van Buren v. United States*, 593 U.S. ___ (2021): The Supreme Court narrowed the scope of CFAA, holding that exceeding authorized use (e.g., misusing information you are allowed to access) does not count as “unauthorized access.” This further limits CFAA’s applicability to public scraping.
- *Ticketmaster v. Prestige Ent.* (C.D. Cal. 2017): Shows that scraping behind technical barriers or violating explicit anti-scraping terms can raise liability under CFAA and contract law. Distinguishes our approach since Columbia has no posted terms or barriers.

### Contract / Terms of Service
- At the time of review, Columbia’s Directory of Classes has no visible Terms of Service or `robots.txt` disallowing scraping.
- If such restrictions appear in the future, we will reassess compliance and consider shifting to licensed access.

### Conclusion
Scraping publicly available factual course data from Columbia’s Directory of Classes — without login requirements or circumvention of access controls — aligns with established U.S. law and court precedent (*HiQ v. LinkedIn*, *Van Buren v. U.S.*), provided we remain responsive to future terms Columbia may impose.

---

## 2. Impact on Website Operations

### Load Management
- Scrapers are rate-limited (1–2 second delays with random jitter) to mimic human browsing.
- Exponential backoff ensures repeated failures don’t stress servers.

### Scope Control
- We only scrape course listings once per term for static fields (titles, prerequisites).
- Highly dynamic fields (enrollment numbers) are refreshed at low frequency, with caching to minimize hits.

### Fail-Safe
- If Columbia signals scraping activity is disruptive, we will pause and open dialogue.

---

## 3. Privacy Considerations
- **What We Collect:** Public course data (titles, codes, times, enrollment limits).
- **What We Do Not Collect:** No personally identifiable student data. No private communications.
- **Instructor Information:** Instructor names are already public on Columbia’s site. We will not extend scraping to private details (emails, phone numbers) beyond what Columbia itself displays publicly.

---

## 4. Ethical Framework
Our team’s ethical commitments:
- **Do No Harm:** Scraping practices must not disrupt Columbia’s IT infrastructure or impose undue server load.
- **Respect Autonomy:** If Columbia requests we stop scraping, we will honor that.
- **Transparency:** Students and advisors should know the data comes from a scraped dataset, not an official Columbia feed.
- **Value Creation:** The dataset must improve access, efficiency, and fairness in course selection.
- **Compliance:** Continually re-assess scraping practices against evolving legal and institutional standards.

---

## 5. Alternative Approaches Considered
- **Official Columbia Open Data API:** Discarded because it requires UNI login, has redistribution restrictions, and is structurally clunky (e.g., term codes like “20131”).
- **Manual Data Entry:** Not scalable or accurate. Too labor-intensive for ~30,000 students and thousands of courses per term.
- **Third-Party APIs (e.g., ADI Course API):** Limited in scope, unofficial, potentially deprecated, and still subject to login requirements.
- **Our Approach:** Scraping public Directory pages with minimal impact, transforming data into clean, reusable JSON.
