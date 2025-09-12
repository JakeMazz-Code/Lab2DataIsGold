"""
Columbia SIS Documentation Scraper with Selenium
Main scraping logic with respectful scraping practices and full pipeline
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import json
import csv
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime
import random
import sys
import os

# Add parent directory to path to import validators and transformers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ColumbiaSISScraper:
    """Selenium-based scraper for Columbia SIS Documentation with exponential backoff and retry logic"""
    
    def __init__(self, base_url: str = "https://doc.sis.columbia.edu/", headless: bool = True):
        self.base_url = base_url
        self.max_retries = 3
        self.base_delay = 2.0  # Base delay in seconds (longer for Selenium)
        self.scraped_data = []
        self.visited_urls = set()
        self.headless = headless
        self.driver = None
        
    def setup_driver(self):
        """Setup Chrome driver with appropriate options"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Additional options for stability and to avoid detection
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Educational Scraper)')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Disable images for faster loading
        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            logger.info("Chrome driver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise
    
    def exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.1)  # Add 10% jitter
        return delay + jitter
    
    def wait_for_page_load(self, timeout: int = 10) -> bool:
        """Wait for page to load completely, including Angular/dynamic content"""
        try:
            # Wait for body element to be present
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Wait for Angular to load (if present)
            time.sleep(2)  # Give Angular time to bootstrap
            
            # Try to wait for specific Angular elements or data attributes
            try:
                # Wait for any ng-app, ng-controller, or data-ng attributes (Angular indicators)
                WebDriverWait(self.driver, 5).until(
                    lambda driver: driver.execute_script("""
                        return document.querySelector('[ng-app], [data-ng-app], [ng-controller], [data-ng-controller]') !== null ||
                               document.querySelector('[ng-repeat], [data-ng-repeat]') !== null ||
                               document.querySelector('.ng-scope') !== null ||
                               document.querySelector('a[href*="subj/"]') !== null;
                    """)
                )
                logger.info("Angular/dynamic content detected and loaded")
            except:
                logger.info("No Angular markers found or timeout waiting for dynamic content")
            
            # Additional wait for any AJAX/dynamic content
            time.sleep(2)
            
            # Try to wait for links to appear
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]"))
                )
            except:
                pass
            
            # Check if page has loaded by executing JavaScript
            page_state = self.driver.execute_script("return document.readyState")
            
            # Scroll to trigger any lazy loading
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight*2/3);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            return page_state == "complete"
            
        except TimeoutException:
            logger.warning("Page load timeout")
            return False
    
    def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page with retry logic and exponential backoff using Selenium"""
        attempt = 0
        
        while attempt < self.max_retries:
            try:
                logger.info(f"Fetching: {url} (Attempt {attempt + 1}/{self.max_retries})")
                
                # Add delay between requests (respectful scraping)
                if attempt > 0:
                    delay = self.exponential_backoff(attempt)
                    logger.info(f"Waiting {delay:.2f} seconds before retry...")
                    time.sleep(delay)
                else:
                    time.sleep(self.base_delay)  # Always wait between requests
                
                # Navigate to URL
                self.driver.get(url)
                
                # Wait for page to load (including Angular content)
                if self.wait_for_page_load():
                    # Try to detect and wait for Angular/dynamic content
                    time.sleep(3)  # Extra wait for dynamic content
                    
                    # Check if this is a department page and try to click on semester
                    if '/subj/' in url and url.count('/') == 5:  # Department page
                        logger.info("Department page detected, looking for semester links...")
                        
                        try:
                            # Look for semester links (Fall 2025, Spring 2025, etc.)
                            semester_links = self.driver.find_elements(By.CSS_SELECTOR, "a")
                            clicked_semester = False
                            
                            for link in semester_links:
                                link_text = link.text.strip()
                                # Check for semester patterns
                                if any(term in link_text for term in ['Fall 202', 'Spring 202', 'Summer 202']):
                                    logger.info(f"Found semester link: {link_text}")
                                    try:
                                        # Scroll to the element
                                        self.driver.execute_script("arguments[0].scrollIntoView(true);", link)
                                        time.sleep(1)
                                        
                                        # Click the semester link
                                        link.click()
                                        logger.info(f"Clicked on semester: {link_text}")
                                        clicked_semester = True
                                        
                                        # Wait for content to load after click
                                        time.sleep(3)
                                        
                                        # Check if new content loaded
                                        WebDriverWait(self.driver, 5).until(
                                            lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "a[href*='/subj/']")) > 0
                                        )
                                        
                                        break  # Stop after clicking first semester
                                    except Exception as e:
                                        logger.warning(f"Could not click semester link: {e}")
                                        # Try JavaScript click as fallback
                                        try:
                                            self.driver.execute_script("arguments[0].click();", link)
                                            logger.info(f"Clicked via JavaScript on semester: {link_text}")
                                            clicked_semester = True
                                            time.sleep(3)
                                            break
                                        except:
                                            continue
                            
                            if clicked_semester:
                                logger.info("Successfully expanded semester content")
                            else:
                                logger.info("No semester links found or clickable")
                                
                        except Exception as e:
                            logger.warning(f"Error handling semester links: {e}")
                    
                    # Check if Angular is present
                    try:
                        is_angular = self.driver.execute_script("""
                            return typeof angular !== 'undefined' || 
                                   document.querySelector('[ng-app]') !== null ||
                                   document.querySelector('[data-ng-app]') !== null;
                        """)
                        
                        if is_angular:
                            logger.info("Angular application detected, waiting for content...")
                            time.sleep(2)
                    except:
                        pass
                    
                    # Get page source after all waits and clicks
                    page_source = self.driver.page_source
                    
                    # Log some debugging info
                    links_count = len(self.driver.find_elements(By.TAG_NAME, "a"))
                    logger.info(f"Page loaded with {links_count} total <a> tags")
                    
                    # Look specifically for course links
                    course_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='-202']")
                    if course_links:
                        logger.info(f"Found {len(course_links)} course links with semester codes")
                    
                    logger.info(f"Successfully fetched: {url}")
                    return page_source
                else:
                    raise TimeoutException("Page did not load completely")
                    
            except (WebDriverException, TimeoutException) as e:
                logger.warning(f"Error fetching {url}: {e}")
                attempt += 1
                
                if attempt >= self.max_retries:
                    logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
                    return None
        
        return None
    def extract_javascript_data(self) -> Dict:
        """Extract any data loaded by JavaScript"""
        js_data = {}
        
        try:
            # Try to extract any JSON data embedded in the page
            scripts = self.driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                script_content = script.get_attribute("innerHTML")
                if script_content and ("window." in script_content or "var " in script_content):
                    # Look for data assignments
                    if "data" in script_content.lower() or "config" in script_content.lower():
                        js_data['has_embedded_data'] = True
                        
            # Check for any React/Vue/Angular indicators
            try:
                react_root = self.driver.find_elements(By.ID, "root")
                if react_root:
                    js_data['framework'] = 'React'
            except:
                pass
                
            # Try to get any API endpoints from network requests (if visible in JS)
            try:
                api_calls = self.driver.execute_script("""
                    return window.performance.getEntriesByType('resource')
                        .filter(e => e.name.includes('api') || e.name.includes('json'))
                        .map(e => e.name);
                """)
                if api_calls:
                    js_data['api_endpoints'] = api_calls[:5]  # Limit to 5
            except:
                pass
                
        except Exception as e:
            logger.debug(f"Could not extract JavaScript data: {e}")
            
        return js_data
    
    def parse_documentation_page(self, html: str, url: str) -> Dict:
        """Parse a documentation page and extract relevant information"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract JavaScript-rendered data
        js_data = self.extract_javascript_data()
        
        # Extract page data
        page_data = {
            'url': url,
            'scraped_at': datetime.now().isoformat(),
            'title': '',
            'description': '',
            'content_sections': [],
            'navigation_links': [],
            'forms': [],
            'metadata': js_data
        }
        
        # Extract title
        title_elem = soup.find('title')
        if title_elem:
            page_data['title'] = title_elem.text.strip()
        
        # Extract main heading
        h1_elem = soup.find('h1')
        if h1_elem:
            page_data['metadata']['main_heading'] = h1_elem.text.strip()
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            page_data['description'] = meta_desc.get('content', '')
        
        # Look for main content areas
        content_selectors = [
            'main', 
            '[role="main"]',
            '.content',
            '.documentation',
            '.doc-content',
            '#content',
            'article',
            'body'
        ]
        
        main_content = None
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = soup.find('body')
        
        if main_content:
            # Extract content sections
            course_info = main_content.find_all(['div', 'p', 'section'], recursive=True)
            
            for i, elem in enumerate(course_info[:20]):
                if elem.text.strip():
                    section_data = {
                        'type': elem.name,
                        'id': elem.get('id', ''),
                        'class': ' '.join(elem.get('class', [])),
                        'headings': [],
                        'paragraphs': [],
                        'lists': [],
                        'code_blocks': []
                    }
                    
                    # Add text content
                    text = elem.text.strip()
                    if text and len(text) > 20:
                        section_data['paragraphs'].append(text[:500])
                    
                    # Look for any headings within
                    for heading in elem.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                        section_data['headings'].append({
                            'level': heading.name,
                            'text': heading.text.strip(),
                            'id': heading.get('id', '')
                        })
                    
                    if section_data['paragraphs'] or section_data['headings']:
                        page_data['content_sections'].append(section_data)
        
        # Extract ALL links - including dynamically loaded ones
        all_links = soup.find_all('a', href=True)
        seen_hrefs = set()
        
        # Also try to get links directly from Selenium
        try:
            selenium_links = self.driver.find_elements(By.TAG_NAME, "a")
            logger.info(f"Found {len(selenium_links)} links via Selenium")
            
            for link_elem in selenium_links:
                try:
                    href = link_elem.get_attribute('href')
                    text = link_elem.text
                    if href and href not in seen_hrefs:
                        seen_hrefs.add(href)
                        
                        # Determine if internal
                        is_internal = False
                        if href and 'doc.sis.columbia.edu' in href:
                            is_internal = True
                        elif href and not href.startswith('http'):
                            is_internal = True
                        
                        # Check for different types of links
                        priority = 'normal'
                        
                        # Letter navigation (A-Z)
                        if text and len(text.strip()) == 1 and text.strip().isalpha():
                            page_data['navigation_links'].append({
                                'text': f"Letter: {text.strip()}",
                                'href': href,
                                'is_internal': is_internal,
                                'priority': 'high'
                            })
                            logger.info(f"Found letter navigation: {text.strip()}")
                        # Semester links - HIGHEST PRIORITY
                        elif text and any(term in text for term in ['Fall 202', 'Spring 202', 'Summer 202', 'Fall202', 'Spring202', 'Summer202']):
                            page_data['navigation_links'].append({
                                'text': f"Semester: {text}",
                                'href': href,
                                'is_internal': is_internal,
                                'priority': 'semester'  # Changed to highest priority
                            })
                            logger.info(f"Found semester link: {text}")
                        # Course links (contain dash and year)
                        elif href and '-202' in href:
                            page_data['navigation_links'].append({
                                'text': text if text else href.split('/')[-1],
                                'href': href,
                                'is_internal': is_internal,
                                'priority': 'course'
                            })
                        else:
                            page_data['navigation_links'].append({
                                'text': text if text else href.split('/')[-1],
                                'href': href,
                                'is_internal': is_internal,
                                'priority': 'normal'
                            })
                except:
                    continue
        except Exception as e:
            logger.warning(f"Could not extract Selenium links: {e}")
        
        # Also parse BeautifulSoup links as backup
        for link in all_links:
            href = link['href']
            link_text = link.text.strip()
            
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            
            if href and href != '#':
                is_internal = False
                if href.startswith('/'):
                    is_internal = True
                elif 'doc.sis.columbia.edu' in href:
                    is_internal = True
                elif not href.startswith('http'):
                    is_internal = True
                
                page_data['navigation_links'].append({
                    'text': link_text if link_text else href,
                    'href': href,
                    'is_internal': is_internal,
                    'priority': 'normal'
                })
        
        # Determine page type
        if '/subj/' in url and '-' in url:
            page_data['metadata']['page_type'] = 'course'
            parts = url.split('/')
            for part in parts:
                if '-' in part:
                    course_parts = part.split('-')
                    if len(course_parts) >= 3:
                        page_data['metadata']['course_code'] = course_parts[0]
                        page_data['metadata']['term'] = course_parts[1]
                        page_data['metadata']['section'] = course_parts[2]
        elif '/subj/' in url:
            page_data['metadata']['page_type'] = 'department'
            parts = url.rstrip('/').split('/')
            if parts:
                page_data['metadata']['department'] = parts[-1]
        else:
            page_data['metadata']['page_type'] = 'main'
        
        # Extract forms
        forms = soup.find_all('form')
        for form in forms[:5]:
            form_data = {
                'action': form.get('action', ''),
                'method': form.get('method', 'get'),
                'inputs': []
            }
            
            for input_elem in form.find_all(['input', 'select', 'textarea']):
                form_data['inputs'].append({
                    'type': input_elem.get('type', 'text'),
                    'name': input_elem.get('name', ''),
                    'placeholder': input_elem.get('placeholder', '')
                })
            
            if form_data['inputs']:
                page_data['forms'].append(form_data)
        
        # Extract tables
        tables = soup.find_all('table')
        if tables:
            page_data['metadata']['table_count'] = len(tables)
            page_data['metadata']['has_data_tables'] = True
        
        return page_data

    def scrape_site(self, max_pages: int = 10) -> List[Dict]:
        """Main scraping method with page limit for respectful scraping"""
        logger.info(f"Starting Selenium scrape of {self.base_url}")
        
        # Initialize driver
        self.setup_driver()
        
        try:
            # Define common department codes at Columbia
            sample_departments = [
                'COMS',  # Computer Science
                'MATH',  # Mathematics
                'STAT',  # Statistics
                'PHYS',  # Physics
                'CHEM',  # Chemistry
                'BIOL',  # Biology
                'ECON',  # Economics
                'ENGL',  # English
                'HIST',  # History
                'PSYC',  # Psychology
            ]
            
            # Start with base URL and force-add some department pages
            # Start with strategic pages
            urls_to_visit = [
                self.base_url,
                # Add subject listing pages that have semester links
                f"{self.base_url}sel/subj-C.html",  # C subjects (includes COMS)
                f"{self.base_url}sel/subj-E.html",  # E subjects (Engineering)
            ]
            
            # Directly add department URLs since we know the structure
            for dept in sample_departments[:min(3, max_pages-1)]:  # Add fewer departments to leave room for semester pages
                dept_url = f"{self.base_url}subj/{dept}/"
                urls_to_visit.append(dept_url)
                logger.info(f"Pre-added department URL: {dept_url}")
            
            pages_scraped = 0
            
            while urls_to_visit and pages_scraped < max_pages:
                current_url = urls_to_visit.pop(0)
                
                # Skip if already visited
                if current_url in self.visited_urls:
                    continue
                
                self.visited_urls.add(current_url)
                
                # Fetch and parse page
                html = self.fetch_page(current_url)
                if html:
                    page_data = self.parse_documentation_page(html, current_url)
                    self.scraped_data.append(page_data)
                    pages_scraped += 1
                    
                    # Log page type
                    page_type = page_data.get('metadata', {}).get('page_type', 'unknown')
                    logger.info(f"Processing {page_type} page: {current_url}")
                    logger.info(f"Found {len(page_data['navigation_links'])} total links")
                    
                    # Extract new URLs to visit
                    links_added = 0
                    semester_links = []  # HIGHEST PRIORITY
                    high_priority_links = []
                    course_links = []  # For actual course pages
                    normal_links = []
                    
                    for link in page_data['navigation_links']:
                        if link['is_internal']:
                            # Build full URL
                            href = link['href']
                            
                            # Handle different URL formats
                            if href.startswith('http'):
                                full_url = href
                            elif href.startswith('/'):
                                full_url = self.base_url.rstrip('/') + href
                            elif href.startswith('subj/'):
                                full_url = self.base_url + href
                            elif href.startswith('./'):
                                # Relative to current directory
                                base_path = '/'.join(current_url.split('/')[:-1])
                                full_url = base_path + '/' + href[2:]
                            elif href.startswith('../'):
                                # Up one directory
                                base_path = '/'.join(current_url.split('/')[:-2])
                                full_url = base_path + '/' + href[3:]
                            else:
                                # Assume relative to base
                                full_url = self.base_url + href
                            
                            # Clean up URL
                            full_url = full_url.replace('//', '/').replace('https:/', 'https://')
                            
                            # Check if it's a Columbia SIS URL and not already queued
                            if 'doc.sis.columbia.edu' in full_url and full_url not in self.visited_urls and full_url not in urls_to_visit:
                                # Check link priority
                                if link.get('priority') == 'semester':
                                    # SEMESTER LINKS - ABSOLUTE HIGHEST PRIORITY
                                    semester_links.append(full_url)
                                    logger.info(f"Found semester link to prioritize: {full_url}")
                                elif '_Fall202' in full_url or '_Spring202' in full_url or '_Summer202' in full_url:
                                    # Also catch semester URLs by pattern
                                    semester_links.append(full_url)
                                    logger.info(f"Found semester URL pattern: {full_url}")
                                elif link.get('priority') == 'high':
                                    # Alphabet navigation links - high priority
                                    high_priority_links.append(full_url)
                                elif '/subj/' in full_url and full_url.count('-') >= 2:
                                    # Individual course page (e.g., COMS-W4156-001)
                                    course_links.append(full_url)
                                    links_added += 1
                                elif '/subj/' in full_url:
                                    # Department page - medium priority
                                    normal_links.append(full_url)
                                else:
                                    # Other pages - low priority
                                    if len(normal_links) < 10:
                                        normal_links.append(full_url)
                    
                    # Add semester links FIRST (absolute highest priority)
                    for url in semester_links[:10]:  # Take more semester links
                        if len(urls_to_visit) < 50:  # Increase queue size
                            urls_to_visit.insert(0, url)  # Add at the beginning
                            logger.info(f"Added SEMESTER link (TOP PRIORITY): {url}")
                    
                    # Add course links second (actual course pages)
                    for url in course_links[:5]:
                        if len(urls_to_visit) < 50:
                            urls_to_visit.insert(len(semester_links), url)  # After semester links
                            logger.info(f"Added course link: {url}")
                    
                    # Add high priority links (alphabet navigation)
                    for url in high_priority_links[:3]:
                        if len(urls_to_visit) < 50:
                            urls_to_visit.append(url)
                            logger.info(f"Added high priority link: {url}")
                    
                    # Then add normal priority links
                    for url in normal_links[:5]:
                        if len(urls_to_visit) < 50:
                            urls_to_visit.append(url)
                    
                    logger.info(f"Scraped {pages_scraped}/{max_pages} pages. Queue size: {len(urls_to_visit)}")
                    
                    # If we're on a department page and found no course links, try constructing some
                    if page_type == 'department' and links_added == 0:
                        dept_code = page_data.get('metadata', {}).get('department', '')
                        if dept_code:
                            # Try common course patterns
                            sample_courses = [
                                f"{self.base_url}subj/{dept_code}/W1001-20243-001/",
                                f"{self.base_url}subj/{dept_code}/W3134-20243-001/",
                                f"{self.base_url}subj/{dept_code}/W4111-20243-001/"
                            ]
                            for course_url in sample_courses[:2]:
                                if course_url not in self.visited_urls and len(urls_to_visit) < 20:
                                    urls_to_visit.append(course_url)
                                    logger.info(f"Added constructed course URL: {course_url}")
            
            logger.info(f"Scraping complete. Total pages scraped: {len(self.scraped_data)}")
            
            # Log summary of what was scraped
            page_types = {}
            for page in self.scraped_data:
                pt = page.get('metadata', {}).get('page_type', 'unknown')
                page_types[pt] = page_types.get(pt, 0) + 1
            logger.info(f"Page types scraped: {page_types}")
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            
        finally:
            # Always close the driver
            if self.driver:
                self.driver.quit()
                logger.info("Chrome driver closed")
        
        return self.scraped_data
    
    def save_to_json(self, filename: str = 'data/raw_output.json'):
        """Save scraped data to JSON file"""
        Path('data').mkdir(exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Data saved to {filename}")
    
    def save_to_csv(self, filename: str = 'data/raw_output.csv'):
        """Save scraped data summary to CSV file"""
        Path('data').mkdir(exist_ok=True)
        
        if not self.scraped_data:
            logger.warning("No data to save")
            return
        
        # Flatten data for CSV
        csv_data = []
        for page in self.scraped_data:
            csv_row = {
                'url': page['url'],
                'title': page['title'],
                'description': page['description'],
                'scraped_at': page['scraped_at'],
                'num_sections': len(page['content_sections']),
                'num_links': len(page['navigation_links']),
                'num_forms': len(page['forms']),
                'has_tables': page['metadata'].get('has_data_tables', False),
                'has_js_framework': page['metadata'].get('framework', '') != '',
                'main_heading': page['metadata'].get('main_heading', ''),
                'diagram_count': page['metadata'].get('diagram_count', 0)
            }
            csv_data.append(csv_row)
        
        # Write to CSV
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = csv_data[0].keys() if csv_data else []
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_data)
        
        logger.info(f"CSV summary saved to {filename}")


def run_pipeline(max_pages: int = 10, headless: bool = True):
    """Run the complete scraping, validation, and transformation pipeline"""
    
    print("\n" + "="*60)
    print("COLUMBIA SIS DOCUMENTATION SCRAPER")
    print("="*60)
    
    # Import validators and transformers
    from validators import DataValidator
    from transformers import DataTransformer
    
    # Step 1: Scraping
    print("\n[1/4] Starting web scraping...")
    print(f"  Target: https://doc.sis.columbia.edu/")
    print(f"  Max pages: {max_pages}")
    print(f"  Mode: {'Headless' if headless else 'Browser visible'}")
    
    scraper = ColumbiaSISScraper(headless=headless)
    
    try:
        scraped_data = scraper.scrape_site(max_pages=max_pages)
        
        # Save raw data
        scraper.save_to_json('data/raw_output.json')
        scraper.save_to_csv('data/raw_output.csv')
        
        print(f"✓ Scraped {len(scraped_data)} pages successfully")
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        print(f"✗ Scraping failed: {e}")
        return False
    
    # Step 2: Validation
    print("\n[2/4] Validating scraped data...")
    
    validator = DataValidator()
    validation_results = validator.validate_dataset(scraped_data)
    
    # Save validation report
    validation_report = validator.generate_report(validation_results)
    Path('data').mkdir(exist_ok=True)
    with open('data/validation_report.txt', 'w') as f:
        f.write(validation_report)
    
    print(f"✓ Validation complete:")
    print(f"  - Pass rate: {validation_results['summary']['pass_rate']:.1f}%")
    print(f"  - Valid pages: {validation_results['valid_pages']}")
    print(f"  - Invalid pages: {validation_results['invalid_pages']}")
    
    # Step 3: Transformation
    print("\n[3/4] Transforming data...")
    
    transformer = DataTransformer()
    transformation_result = transformer.transform_dataset(scraped_data)
    
    # Save transformed data
    transformer.save_transformed_data('data')
    
    print(f"✓ Transformation complete:")
    print(f"  - Pages transformed: {len(transformation_result['transformed_data'])}")
    print(f"  - Categories found: {len(transformation_result['analytics']['categories'])}")
    print(f"  - Top keywords extracted: {len(transformation_result['analytics']['top_keywords'])}")
    
    # Step 4: Generate final output
    print("\n[4/4] Generating final output...")
    
    # Create sample output for documentation
    sample_output = {
        'metadata': {
            'scrape_date': datetime.now().isoformat(),
            'total_pages': len(transformation_result['transformed_data']),
            'source_url': 'https://doc.sis.columbia.edu/',
            'scraper_version': '1.0.0'
        },
        'summary_statistics': transformation_result['analytics'],
        'sample_pages': transformation_result['transformed_data'][:3] if transformation_result['transformed_data'] else []
    }
    
    with open('data/sample_output.json', 'w', encoding='utf-8') as f:
        json.dump(sample_output, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Sample output saved to data/sample_output.json")
    
    # Print final summary
    print("\n" + "="*60)
    print("PIPELINE COMPLETE!")
    print("="*60)
    print("\nGenerated Files:")
    print("  - data/raw_output.json (raw scraped data)")
    print("  - data/raw_output.csv (CSV summary)")
    print("  - data/validation_report.txt")
    print("  - data/transformed_data.json")
    print("  - data/analytics.json")
    print("  - data/transformation_report.txt")
    print("  - data/sample_output.json")
    
    # Print key insights
    if transformation_result['analytics']['top_keywords']:
        print("\nTop 5 Keywords Found:")
        for keyword in transformation_result['analytics']['top_keywords'][:5]:
            print(f"  - {keyword}")
    
    if transformation_result['analytics']['categories']:
        print("\nContent Categories:")
        for category, count in list(transformation_result['analytics']['categories'].items())[:5]:
            print(f"  - {category}: {count} pages")
    
    return True


def main():
    """Main entry point"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Columbia SIS Documentation Scraper')
    parser.add_argument('--pages', type=int, default=10, help='Maximum number of pages to scrape (default: 10)')
    parser.add_argument('--show-browser', action='store_true', help='Show browser window during scraping')
    parser.add_argument('--scrape-only', action='store_true', help='Only run scraping without validation/transformation')
    
    args = parser.parse_args()
    
    # Create data directory if it doesn't exist
    Path('data').mkdir(exist_ok=True)
    
    if args.scrape_only:
        # Just run the scraper
        scraper = ColumbiaSISScraper(headless=not args.show_browser)
        try:
            scraped_data = scraper.scrape_site(max_pages=args.pages)
            scraper.save_to_json('data/raw_output.json')
            scraper.save_to_csv('data/raw_output.csv')
            print(f"\n✓ Scraped {len(scraped_data)} pages successfully")
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            sys.exit(1)
    else:
        # Run the full pipeline
        success = run_pipeline(
            max_pages=args.pages,
            headless=not args.show_browser
        )
        
        if success:
            print("\n✨ All done! Check the data/ directory for results.")
        else:
            print("\n❌ Pipeline failed. Check pipeline.log for details.")
            sys.exit(1)


if __name__ == "__main__":
    main()