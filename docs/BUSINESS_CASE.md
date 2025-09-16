# Market analysis and pricing

Data Opportunity Brief: Better Course Search for Columbia Students
Problem Statement & Market Opportunity
Problem: Columbia students struggle to compare and select courses because tools like Vergil and the Directory of Classes are outdated and hard to filter. This frustrates students and advisors, and makes enrollment less efficient.
Opportunity: Create a clean, structured JSON dataset of all courses—continuously updated and filterable by time, instructor, prerequisites, and availability. Students get a modern search tool, and Columbia can integrate the dataset into advising systems or portals without building it from scratch.
Market Size Estimate:
Students: ~30,000. At 10% adoption paying $10/year → $30,000+ annual revenue.
Columbia: A single institutional license (~$25k–$50k/year) could outweigh B2C revenue, since the university invests in improving digital tools and student satisfaction.

Why This Data Isn’t Easily Available
Columbia does offer an Open Data API, but it requires UNI login, limiting access to enrolled students. It also has redistribution restrictions, no public search UI or flexible filters, and has a clunky structure (e.g., term codes like “20131” for Spring 2013).

Target Users & Willingness to Pay
Students: Frustrated by clunky tools, willing to pay for faster, smarter course discovery.
Advisors & Student Orgs: Could license access to streamline planning and guidance.
Columbia (Institutional Buyer): Strong incentive to license the dataset/platform (~$25k–$50k/year) to improve advising efficiency, boost student satisfaction, and avoid costly in-house development.

Competitive Landscape
Product
Limitations
Columbia Open Data API
Requires UNI login; clunky; no UI; legal restrictions
ADI Course API (unofficial)
Requires login; potentially deprecated
soid’s JSON scraper (GitHub)
Raw data only; no interface; uncertain maintenance
peqod.com
Partial solution; lacks control and reliability

Our Edge: Public access, custom filters, real-time scraping, and a clean JSON output—built for students, not admins.


Scraping Complexity Matrix
Challenge
Difficulty (1–5)
Solution Strategy
Dynamic JS content
1 – Low
Most data is in plain HTML. Scrape with requests + BeautifulSoup.
Rate limiting
1 – Low
No visible rate limits. Add 1–2 second delays + random jitter to avoid detection.
Data structure variations
3 – Moderate
Course listings vary by term and filter. Write flexible parsers with fallback logic for missing fields.
Session management
1 – Low
Public site, no login or cookies needed. Simple GET requests work.


Ethical & Legal Analysis
No robots.txt
No terms of service to be found
WIll use exponential backoff/other ratelimiting measures
