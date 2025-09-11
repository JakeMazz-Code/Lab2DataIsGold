# Data transformation pipeline
"""
Data Transformation Pipeline for Columbia SIS Scraper
Transforms raw scraped data into structured, analysis-ready format
"""

import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import hashlib
import logging
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


class DataTransformer:
    """Transform raw scraped data into structured format with insights"""
    
    def __init__(self):
        self.transformed_data = []
        self.analytics = {
            'total_pages': 0,
            'total_sections': 0,
            'total_links': 0,
            'content_statistics': {},
            'navigation_structure': {},
            'documentation_categories': []
        }
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s\-.,!?;:()\[\]\'"/]', '', text)
        
        # Trim
        text = text.strip()
        
        return text
    
    def extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """Extract keywords from text using simple frequency analysis"""
        if not text:
            return []
        
        # Common stop words to exclude
        stop_words = {
            'the', 'is', 'at', 'which', 'on', 'a', 'an', 'as', 'are', 'was',
            'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
            'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
            'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
            'some', 'such', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'just', 'in', 'of', 'to', 'for', 'with', 'from', 'up', 'out', 'if',
            'about', 'into', 'through', 'during', 'before', 'after', 'above',
            'below', 'between', 'under', 'again', 'further', 'then', 'once'
        }
        
        # Tokenize and clean
        words = re.findall(r'\b[a-z]+\b', text.lower())
        
        # Filter out stop words and short words
        words = [w for w in words if w not in stop_words and len(w) > 3]
        
        # Count frequencies
        word_counts = Counter(words)
        
        # Return top keywords
        return [word for word, _ in word_counts.most_common(top_n)]
    
    def categorize_page(self, page_data: Dict) -> str:
        """Categorize page based on content and structure"""
        title = page_data.get('title', '').lower()
        url = page_data.get('url', '').lower()
        
        # Define category patterns
        categories = {
            'API Documentation': ['api', 'endpoint', 'request', 'response', 'method'],
            'User Guide': ['guide', 'how to', 'tutorial', 'getting started', 'user'],
            'Reference': ['reference', 'specification', 'schema', 'model', 'structure'],
            'Administration': ['admin', 'configuration', 'settings', 'management', 'setup'],
            'Security': ['security', 'authentication', 'authorization', 'permission', 'access'],
            'FAQ': ['faq', 'frequently asked', 'question', 'answer', 'help'],
            'Release Notes': ['release', 'version', 'changelog', 'update', 'new feature'],
            'Integration': ['integration', 'connect', 'third-party', 'external', 'webhook'],
            'Troubleshooting': ['troubleshoot', 'error', 'problem', 'issue', 'debug'],
            'Overview': ['overview', 'introduction', 'about', 'welcome', 'home']
        }
        
        # Check title and URL for category keywords
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in title or keyword in url:
                    return category
        
        # Check content for category keywords
        content_text = ""
        for section in page_data.get('content_sections', []):
            for heading in section.get('headings', []):
                content_text += " " + heading.get('text', '').lower()
        
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in content_text:
                    return category
        
        return 'General Documentation'
    
    def calculate_content_metrics(self, page_data: Dict) -> Dict:
        """Calculate various content metrics for a page"""
        metrics = {
            'word_count': 0,
            'heading_count': 0,
            'paragraph_count': 0,
            'list_count': 0,
            'code_block_count': 0,
            'link_density': 0,
            'content_depth': 0,
            'readability_score': 0
        }
        
        total_text = ""
        
        for section in page_data.get('content_sections', []):
            # Count headings
            metrics['heading_count'] += len(section.get('headings', []))
            
            # Count and aggregate paragraphs
            paragraphs = section.get('paragraphs', [])
            metrics['paragraph_count'] += len(paragraphs)
            for para in paragraphs:
                total_text += " " + para
            
            # Count lists
            metrics['list_count'] += len(section.get('lists', []))
            
            # Count code blocks
            metrics['code_block_count'] += len(section.get('code_blocks', []))
            
            # Add list items to text
            for list_item in section.get('lists', []):
                for item in list_item.get('items', []):
                    total_text += " " + item
        
        # Calculate word count
        words = total_text.split()
        metrics['word_count'] = len(words)
        
        # Calculate link density
        link_count = len(page_data.get('navigation_links', []))
        if metrics['word_count'] > 0:
            metrics['link_density'] = round(link_count / metrics['word_count'] * 100, 2)
        
        # Calculate content depth (average section complexity)
        if len(page_data.get('content_sections', [])) > 0:
            metrics['content_depth'] = round(
                (metrics['heading_count'] + metrics['paragraph_count'] + metrics['list_count']) / 
                len(page_data.get('content_sections', [])), 2
            )
        
        # Simple readability score (based on average sentence length)
        sentences = re.split(r'[.!?]+', total_text)
        sentences = [s for s in sentences if len(s.strip()) > 0]
        if sentences:
            avg_sentence_length = len(words) / len(sentences)
            # Simple readability: shorter sentences = higher score
            metrics['readability_score'] = max(0, min(100, 100 - (avg_sentence_length - 15) * 3))
        
        return metrics
    
    def extract_navigation_hierarchy(self, pages: List[Dict]) -> Dict:
        """Extract navigation hierarchy from all pages"""
        hierarchy = {
            'root_pages': [],
            'page_relationships': defaultdict(list),
            'common_navigation': Counter(),
            'depth_levels': defaultdict(int)
        }
        
        for page in pages:
            url = page.get('url', '')
            
            # Determine depth level based on URL structure
            path_parts = url.replace('https://', '').replace('http://', '').split('/')
            depth = len([p for p in path_parts if p]) - 1
            hierarchy['depth_levels'][url] = depth
            
            if depth <= 1:
                hierarchy['root_pages'].append(url)
            
            # Track navigation patterns
            for link in page.get('navigation_links', []):
                link_text = link.get('text', '')
                if link_text:
                    hierarchy['common_navigation'][link_text] += 1
                    
                    # Track page relationships
                    if link.get('is_internal'):
                        hierarchy['page_relationships'][url].append(link.get('href', ''))
        
        # Get most common navigation items
        hierarchy['top_navigation'] = [
            item for item, _ in hierarchy['common_navigation'].most_common(10)
        ]
        
        return dict(hierarchy)
    
    def generate_content_summary(self, page_data: Dict) -> str:
        """Generate a concise summary of page content"""
        summary_parts = []
        
        # Add title
        title = page_data.get('title', 'Untitled')
        summary_parts.append(f"Page: {title}")
        
        # Add description if available
        if page_data.get('description'):
            summary_parts.append(f"Description: {page_data['description'][:100]}")
        
        # Count content types
        section_count = len(page_data.get('content_sections', []))
        if section_count > 0:
            summary_parts.append(f"Contains {section_count} content sections")
        
        # Extract main topics from headings
        all_headings = []
        for section in page_data.get('content_sections', []):
            for heading in section.get('headings', []):
                all_headings.append(heading.get('text', ''))
        
        if all_headings:
            summary_parts.append(f"Main topics: {', '.join(all_headings[:5])}")
        
        return " | ".join(summary_parts)
    
    def transform_page(self, page_data: Dict) -> Dict:
        """Transform a single page of scraped data"""
        # Generate unique ID for the page
        page_id = hashlib.md5(page_data.get('url', '').encode()).hexdigest()[:12]
        
        # Extract all text content for analysis
        all_text = ""
        for section in page_data.get('content_sections', []):
            for para in section.get('paragraphs', []):
                all_text += " " + para
        
        # Transform the data
        transformed = {
            'id': page_id,
            'url': page_data.get('url', ''),
            'title': self.clean_text(page_data.get('title', '')),
            'category': self.categorize_page(page_data),
            'scraped_at': page_data.get('scraped_at', ''),
            'summary': self.generate_content_summary(page_data),
            'keywords': self.extract_keywords(all_text),
            'metrics': self.calculate_content_metrics(page_data),
            'content': {
                'description': self.clean_text(page_data.get('description', '')),
                'main_heading': page_data.get('metadata', {}).get('main_heading', ''),
                'section_count': len(page_data.get('content_sections', [])),
                'sections': self._transform_sections(page_data.get('content_sections', [])),
                'has_forms': len(page_data.get('forms', [])) > 0,
                'has_tables': page_data.get('metadata', {}).get('has_data_tables', False),
                'has_code_examples': any(
                    section.get('code_blocks', []) 
                    for section in page_data.get('content_sections', [])
                )
            },
            'navigation': {
                'link_count': len(page_data.get('navigation_links', [])),
                'internal_links': [
                    link for link in page_data.get('navigation_links', [])
                    if link.get('is_internal')
                ][:10],  # Limit to 10 for summary
                'external_links': [
                    link for link in page_data.get('navigation_links', [])
                    if not link.get('is_internal')
                ][:5]  # Limit to 5 for summary
            },
            'technical_indicators': {
                'uses_javascript': page_data.get('metadata', {}).get('framework') is not None,
                'javascript_framework': page_data.get('metadata', {}).get('framework', ''),
                'has_api_endpoints': bool(page_data.get('metadata', {}).get('api_endpoints', [])),
                'diagram_count': page_data.get('metadata', {}).get('diagram_count', 0)
            }
        }
        
        return transformed
    
    def _transform_sections(self, sections: List[Dict]) -> List[Dict]:
        """Transform content sections into simplified format"""
        transformed_sections = []
        
        for section in sections[:10]:  # Limit to 10 sections
            transformed_section = {
                'type': section.get('type', ''),
                'heading_hierarchy': [],
                'content_types': [],
                'text_preview': ""
            }
            
            # Extract heading hierarchy
            for heading in section.get('headings', []):
                transformed_section['heading_hierarchy'].append({
                    'level': heading.get('level', ''),
                    'text': self.clean_text(heading.get('text', ''))
                })
            
            # Identify content types
            if section.get('paragraphs'):
                transformed_section['content_types'].append('text')
                transformed_section['text_preview'] = self.clean_text(
                    section['paragraphs'][0][:200] if section['paragraphs'] else ""
                )
            
            if section.get('lists'):
                transformed_section['content_types'].append('lists')
            
            if section.get('code_blocks'):
                transformed_section['content_types'].append('code')
            
            transformed_sections.append(transformed_section)
        
        return transformed_sections
    
    def calculate_analytics(self, transformed_data: List[Dict]) -> Dict:
        """Calculate analytics across all transformed data"""
        analytics = {
            'total_pages': len(transformed_data),
            'categories': Counter(),
            'avg_metrics': {},
            'content_distribution': {},
            'keyword_frequency': Counter(),
            'technical_summary': {}
        }
        
        # Aggregate metrics
        metric_sums = defaultdict(float)
        metric_counts = defaultdict(int)
        
        for page in transformed_data:
            # Count categories
            analytics['categories'][page['category']] += 1
            
            # Aggregate metrics
            for metric, value in page['metrics'].items():
                metric_sums[metric] += value
                metric_counts[metric] += 1
            
            # Aggregate keywords
            for keyword in page['keywords']:
                analytics['keyword_frequency'][keyword] += 1
        
        # Calculate averages
        for metric in metric_sums:
            if metric_counts[metric] > 0:
                analytics['avg_metrics'][metric] = round(
                    metric_sums[metric] / metric_counts[metric], 2
                )
        
        # Content distribution
        has_forms = sum(1 for p in transformed_data if p['content']['has_forms'])
        has_tables = sum(1 for p in transformed_data if p['content']['has_tables'])
        has_code = sum(1 for p in transformed_data if p['content']['has_code_examples'])
        
        analytics['content_distribution'] = {
            'pages_with_forms': has_forms,
            'pages_with_tables': has_tables,
            'pages_with_code': has_code,
            'avg_sections_per_page': round(
                sum(p['content']['section_count'] for p in transformed_data) / len(transformed_data), 2
            ) if transformed_data else 0
        }
        
        # Technical summary
        uses_js = sum(1 for p in transformed_data if p['technical_indicators']['uses_javascript'])
        frameworks = Counter(
            p['technical_indicators']['javascript_framework'] 
            for p in transformed_data 
            if p['technical_indicators']['javascript_framework']
        )
        
        analytics['technical_summary'] = {
            'pages_using_javascript': uses_js,
            'frameworks_detected': dict(frameworks),
            'pages_with_api_endpoints': sum(
                1 for p in transformed_data 
                if p['technical_indicators']['has_api_endpoints']
            )
        }
        
        # Top keywords
        analytics['top_keywords'] = [
            keyword for keyword, _ in analytics['keyword_frequency'].most_common(20)
        ]
        
        return analytics
    
    def transform_dataset(self, raw_data: List[Dict]) -> Dict:
        """Transform entire dataset and generate analytics"""
        logger.info(f"Starting transformation of {len(raw_data)} pages")
        
        # Transform each page
        self.transformed_data = []
        for page_data in raw_data:
            try:
                transformed = self.transform_page(page_data)
                self.transformed_data.append(transformed)
            except Exception as e:
                logger.error(f"Error transforming page {page_data.get('url', 'unknown')}: {e}")
        
        # Extract navigation hierarchy
        navigation_hierarchy = self.extract_navigation_hierarchy(raw_data)
        
        # Calculate analytics
        self.analytics = self.calculate_analytics(self.transformed_data)
        self.analytics['navigation_structure'] = navigation_hierarchy
        
        logger.info(f"Transformation complete. {len(self.transformed_data)} pages transformed")
        
        return {
            'transformed_data': self.transformed_data,
            'analytics': self.analytics,
            'transformation_metadata': {
                'transformed_at': datetime.now().isoformat(),
                'total_pages_processed': len(raw_data),
                'total_pages_transformed': len(self.transformed_data),
                'transformation_success_rate': round(
                    len(self.transformed_data) / len(raw_data) * 100, 2
                ) if raw_data else 0
            }
        }
    
    def save_transformed_data(self, output_dir: str = 'data'):
        """Save transformed data and analytics to files"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Save transformed data
        with open(output_path / 'transformed_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.transformed_data, f, indent=2, ensure_ascii=False)
        
        # Save analytics
        # Convert Counter objects to dict for JSON serialization
        analytics_json = json.loads(json.dumps(self.analytics, default=str))
        with open(output_path / 'analytics.json', 'w', encoding='utf-8') as f:
            json.dump(analytics_json, f, indent=2, ensure_ascii=False)
        
        # Generate and save summary report
        report = self.generate_transformation_report()
        with open(output_path / 'transformation_report.txt', 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.info(f"Transformed data saved to {output_path}")
    
    def generate_transformation_report(self) -> str:
        """Generate a human-readable transformation report"""
        report = []
        report.append("="*60)
        report.append("DATA TRANSFORMATION REPORT")
        report.append("="*60)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        # Summary statistics
        report.append("SUMMARY STATISTICS:")
        report.append(f"  Total Pages Transformed: {self.analytics['total_pages']}")
        report.append("")
        
        # Category distribution
        report.append("CONTENT CATEGORIES:")
        for category, count in self.analytics['categories'].most_common():
            report.append(f"  {category}: {count} pages")
        report.append("")
        
        # Average metrics
        report.append("AVERAGE CONTENT METRICS:")
        for metric, value in self.analytics['avg_metrics'].items():
            report.append(f"  {metric.replace('_', ' ').title()}: {value}")
        report.append("")
        
        # Content distribution
        report.append("CONTENT FEATURES:")
        for feature, value in self.analytics['content_distribution'].items():
            report.append(f"  {feature.replace('_', ' ').title()}: {value}")
        report.append("")
        
        # Technical summary
        report.append("TECHNICAL ANALYSIS:")
        for feature, value in self.analytics['technical_summary'].items():
            if isinstance(value, dict):
                report.append(f"  {feature.replace('_', ' ').title()}:")
                for k, v in value.items():
                    report.append(f"    - {k}: {v}")
            else:
                report.append(f"  {feature.replace('_', ' ').title()}: {value}")
        report.append("")
        
        # Top keywords
        report.append("TOP 10 KEYWORDS:")
        for keyword in self.analytics['top_keywords'][:10]:
            report.append(f"  - {keyword}")
        report.append("")
        
        # Navigation structure insights
        if 'navigation_structure' in self.analytics:
            nav = self.analytics['navigation_structure']
            report.append("NAVIGATION INSIGHTS:")
            report.append(f"  Root Pages: {len(nav.get('root_pages', []))}")
            if 'top_navigation' in nav:
                report.append("  Most Common Navigation Items:")
                for item in nav['top_navigation'][:5]:
                    report.append(f"    - {item}")
        
        report.append("")
        report.append("="*60)
        
        return "\n".join(report)


def main():
    """Main execution for testing transformer"""
    import json
    
    # Load raw data if it exists
    raw_data_path = Path('data/raw_output.json')
    
    if raw_data_path.exists():
        with open(raw_data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Transform the data
        transformer = DataTransformer()
        result = transformer.transform_dataset(raw_data)
        
        # Save transformed data
        transformer.save_transformed_data()
        
        # Print summary
        print(transformer.generate_transformation_report())
    else:
        print("No raw data found. Please run scraper.py first.")


if __name__ == "__main__":
    main()
