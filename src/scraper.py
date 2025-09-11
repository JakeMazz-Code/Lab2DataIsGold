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
        """Wait for page to load completely"""
        try:
            # Wait for body element to be present
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Additional wait for any dynamic content
            time.sleep(1)
            
            # Check if page has loaded by executing JavaScript
            page_state = self.driver.execute_script("return document.readyState")
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
                
                # Wait for page to load
                if self.wait_for_page_load():
                    # Scroll to load any lazy-loaded content
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                    time.sleep(0.5)
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.5)
                    
                    # Get page source
                    page_source = self.driver.page_source
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
        
        # Look for main content areas (common in documentation sites)
        content_selectors = [
            'main', 
            '[role="main"]',
            '.content',
            '.documentation',
            '.doc-content',
            '#content',
            'article'
        ]
        
        main_content = None
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        # If no main content found, use body
        if not main_content:
            main_content = soup.find('body')
        
        if main_content:
            # Extract content sections
            sections = main_content.find_all(['section', 'div'], recursive=True)
            
            for section in sections[:20]:  # Limit sections
                section_data = {
                    'type': section.name,
                    'id': section.get('id', ''),
                    'class': ' '.join(section.get('class', [])),
                    'headings': [],
                    'paragraphs': [],
                    'lists': [],
                    'code_blocks': []
                }
                
                # Extract headings
                for heading in section.find_all(['h2', 'h3', 'h4', 'h5']):
                    section_data['headings'].append({
                        'level': heading.name,
                        'text': heading.text.strip(),
                        'id': heading.get('id', '')
                    })
                
                # Extract paragraphs
                for para in section.find_all('p'):
                    text = para.text.strip()
                    if text and len(text) > 20:  # Skip very short paragraphs
                        section_data['paragraphs'].append(text[:500])
                
                # Extract lists
                for list_elem in section.find_all(['ul', 'ol']):
                    list_items = [li.text.strip() for li in list_elem.find_all('li', recursive=False)]
                    if list_items:
                        section_data['lists'].append({
                            'type': list_elem.name,
                            'items': list_items[:10]
                        })
                
                # Extract code blocks
                for code in section.find_all(['code', 'pre']):
                    code_text = code.text.strip()
                    if code_text:
                        section_data['code_blocks'].append({
                            'language': code.get('class', [''])[0] if code.get('class') else 'unknown',
                            'content': code_text[:300]  # Limit code length
                        })
                
                # Only add section if it has content
                if any([section_data['headings'], section_data['paragraphs'], 
                       section_data['lists'], section_data['code_blocks']]):
                    page_data['content_sections'].append(section_data)
        
        # Extract navigation links - broader search
        # Try multiple strategies to find links
        nav_areas = soup.find_all(['nav', '[role="navigation"]', '.navigation', '.sidebar'])
        
        # If no navigation areas found, search entire page for links
        if not nav_areas:
            nav_areas = [soup]  # Search entire page
            
        for nav in nav_areas:
            for link in nav.find_all('a', href=True)[:50]:  # Increased limit
                href = link['href
        
        # Extract forms (common in documentation for search or examples)
        forms = soup.find_all('form')
        for form in forms[:5]:  # Limit forms
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
        
        # Extract images with alt text (for documentation diagrams)
        images = soup.find_all('img', alt=True)
        if images:
            page_data['metadata']['diagram_count'] = len(images)
            page_data['metadata']['diagram_descriptions'] = [
                img.get('alt', '')[:100] for img in images[:5]
            ]
        
        return page_data
    
    def scrape_site(self, max_pages: int = 10) -> List[Dict]:
        """Main scraping method with page limit for respectful scraping"""
        logger.info(f"Starting Selenium scrape of {self.base_url}")
        
        # Initialize driver
        self.setup_driver()
        
        try:
            # Start with base URL
            urls_to_visit = [self.base_url]
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
                    
                    # Extract new URLs to visit (limited crawling)
                    for link in page_data['navigation_links'][:5]:
                        if link['is_internal'] and link['href'] not in self.visited_urls:
                            if link['href'].startswith('/'):
                                full_url = self.base_url.rstrip('/') + link['href']
                            elif link['href'].startswith('http'):
                                full_url = link['href']
                            else:
                                full_url = self.base_url.rstrip('/') + '/' + link['href']
                            
                            if full_url not in self.visited_urls and len(urls_to_visit) < 20:
                                urls_to_visit.append(full_url)
                    
                    logger.info(f"Scraped {pages_scraped}/{max_pages} pages. Queue size: {len(urls_to_visit)}")
            
            logger.info(f"Scraping complete. Total pages scraped: {len(self.scraped_data)}")
            
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