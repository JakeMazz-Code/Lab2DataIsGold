# Data validation rules
"""
Data Validation Rules for Columbia SIS Scraper
Ensures data quality and consistency
"""

import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates scraped data for quality assurance"""
    
    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []
        self.stats = {
            'total_validated': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0
        }
    
    def validate_url(self, url: str) -> Tuple[bool, str]:
        """Validate URL format and structure"""
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False, "Invalid URL structure"
            
            if result.scheme not in ['http', 'https']:
                return False, "URL must use HTTP or HTTPS"
            
            # Check for Columbia domain
            if 'columbia.edu' not in result.netloc:
                self.validation_warnings.append(f"URL not from columbia.edu domain: {url}")
            
            return True, "Valid URL"
            
        except Exception as e:
            return False, f"URL validation error: {str(e)}"
    
    def validate_title(self, title: str) -> Tuple[bool, str]:
        """Validate page title"""
        if not title:
            return False, "Title is empty"
        
        if len(title) < 3:
            return False, "Title too short (less than 3 characters)"
        
        if len(title) > 200:
            self.validation_warnings.append(f"Title unusually long: {len(title)} characters")
        
        # Check for common placeholder titles
        placeholder_patterns = [
            r'^untitled',
            r'^new page',
            r'^document\d*$',
            r'^page\d*$'
        ]
        
        for pattern in placeholder_patterns:
            if re.match(pattern, title.lower()):
                self.validation_warnings.append(f"Possible placeholder title: {title}")
                break
        
        return True, "Valid title"
    
    def validate_timestamp(self, timestamp: str) -> Tuple[bool, str]:
        """Validate timestamp format"""
        try:
            # Try to parse ISO format
            datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return True, "Valid timestamp"
        except Exception as e:
            return False, f"Invalid timestamp format: {str(e)}"
    
    def validate_content_sections(self, sections: List[Dict]) -> Tuple[bool, str]:
        """Validate content sections structure and content"""
        if not sections:
            self.validation_warnings.append("No content sections found")
            return True, "No sections to validate"
        
        errors = []
        
        for i, section in enumerate(sections):
            # Check required fields
            if 'type' not in section:
                errors.append(f"Section {i} missing 'type' field")
            
            # Validate headings
            if 'headings' in section:
                for heading in section['headings']:
                    if not isinstance(heading, dict):
                        errors.append(f"Section {i} has invalid heading format")
                    elif 'text' not in heading or 'level' not in heading:
                        errors.append(f"Section {i} heading missing required fields")
            
            # Validate paragraphs
            if 'paragraphs' in section:
                for j, para in enumerate(section['paragraphs']):
                    if not isinstance(para, str):
                        errors.append(f"Section {i} paragraph {j} is not a string")
                    elif len(para) < 10:
                        self.validation_warnings.append(f"Section {i} has very short paragraph")
            
            # Validate lists
            if 'lists' in section:
                for list_item in section['lists']:
                    if not isinstance(list_item, dict):
                        errors.append(f"Section {i} has invalid list format")
                    elif 'items' not in list_item or 'type' not in list_item:
                        errors.append(f"Section {i} list missing required fields")
        
        if errors:
            return False, "; ".join(errors)
        
        return True, "Valid content sections"
    
    def validate_navigation_links(self, links: List[Dict]) -> Tuple[bool, str]:
        """Validate navigation links"""
        if not links:
            self.validation_warnings.append("No navigation links found")
            return True, "No links to validate"
        
        errors = []
        valid_links = 0
        
        for i, link in enumerate(links):
            # Check required fields
            if 'href' not in link:
                errors.append(f"Link {i} missing 'href' field")
                continue
            
            if 'text' not in link:
                errors.append(f"Link {i} missing 'text' field")
                continue
            
            # Validate href format
            href = link['href']
            if not href:
                errors.append(f"Link {i} has empty href")
            elif href == '#':
                self.validation_warnings.append(f"Link {i} is anchor-only link")
            elif href.startswith('javascript:'):
                self.validation_warnings.append(f"Link {i} is JavaScript link")
            else:
                valid_links += 1
            
            # Check for link text
            if not link['text'].strip():
                self.validation_warnings.append(f"Link {i} has empty text")
        
        if valid_links == 0 and len(links) > 0:
            errors.append("No valid navigation links found")
        
        if errors:
            return False, "; ".join(errors)
        
        return True, f"Valid navigation links ({valid_links}/{len(links)} valid)"
    
    def validate_metadata(self, metadata: Dict) -> Tuple[bool, str]:
        """Validate metadata fields"""
        warnings = []
        
        # Check for suspicious patterns
        if metadata.get('table_count', 0) > 50:
            warnings.append(f"Unusually high table count: {metadata['table_count']}")
        
        if metadata.get('diagram_count', 0) > 100:
            warnings.append(f"Unusually high diagram count: {metadata['diagram_count']}")
        
        # Check for framework detection
        if 'framework' in metadata:
            valid_frameworks = ['React', 'Vue', 'Angular', 'jQuery']
            if metadata['framework'] not in valid_frameworks:
                warnings.append(f"Unknown framework detected: {metadata['framework']}")
        
        if warnings:
            self.validation_warnings.extend(warnings)
        
        return True, "Metadata validated"
    
    def validate_page(self, page_data: Dict) -> Dict:
        """Validate a complete page data structure"""
        validation_result = {
            'url': page_data.get('url', 'unknown'),
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Required fields
        required_fields = ['url', 'scraped_at', 'title']
        for field in required_fields:
            if field not in page_data:
                validation_result['errors'].append(f"Missing required field: {field}")
                validation_result['valid'] = False
        
        # Validate URL
        if 'url' in page_data:
            valid, msg = self.validate_url(page_data['url'])
            if not valid:
                validation_result['errors'].append(f"URL: {msg}")
                validation_result['valid'] = False
        
        # Validate title
        if 'title' in page_data:
            valid, msg = self.validate_title(page_data['title'])
            if not valid:
                validation_result['errors'].append(f"Title: {msg}")
                validation_result['valid'] = False
        
        # Validate timestamp
        if 'scraped_at' in page_data:
            valid, msg = self.validate_timestamp(page_data['scraped_at'])
            if not valid:
                validation_result['errors'].append(f"Timestamp: {msg}")
                validation_result['valid'] = False
        
        # Validate content sections
        if 'content_sections' in page_data:
            valid, msg = self.validate_content_sections(page_data['content_sections'])
            if not valid:
                validation_result['errors'].append(f"Content: {msg}")
                validation_result['valid'] = False
        
        # Validate navigation links
        if 'navigation_links' in page_data:
            valid, msg = self.validate_navigation_links(page_data['navigation_links'])
            if not valid:
                validation_result['errors'].append(f"Links: {msg}")
                validation_result['valid'] = False
        
        # Validate metadata
        if 'metadata' in page_data:
            valid, msg = self.validate_metadata(page_data['metadata'])
            if not valid:
                validation_result['errors'].append(f"Metadata: {msg}")
                validation_result['valid'] = False
        
        # Add any accumulated warnings
        validation_result['warnings'] = self.validation_warnings.copy()
        self.validation_warnings.clear()
        
        # Update stats
        self.stats['total_validated'] += 1
        if validation_result['valid']:
            self.stats['passed'] += 1
        else:
            self.stats['failed'] += 1
        self.stats['warnings'] += len(validation_result['warnings'])
        
        return validation_result
    
    def validate_dataset(self, data: List[Dict]) -> Dict:
        """Validate entire dataset"""
        results = {
            'total_pages': len(data),
            'valid_pages': 0,
            'invalid_pages': 0,
            'validation_details': [],
            'summary': {}
        }
        
        for page_data in data:
            validation_result = self.validate_page(page_data)
            results['validation_details'].append(validation_result)
            
            if validation_result['valid']:
                results['valid_pages'] += 1
            else:
                results['invalid_pages'] += 1
        
        # Generate summary
        results['summary'] = {
            'total_validated': self.stats['total_validated'],
            'passed': self.stats['passed'],
            'failed': self.stats['failed'],
            'total_warnings': self.stats['warnings'],
            'pass_rate': (self.stats['passed'] / self.stats['total_validated'] * 100) 
                        if self.stats['total_validated'] > 0 else 0,
            'common_errors': self._get_common_errors(results['validation_details']),
            'common_warnings': self._get_common_warnings(results['validation_details'])
        }
        
        return results
    
    def _get_common_errors(self, details: List[Dict]) -> List[str]:
        """Extract common error patterns"""
        error_counts = {}
        for detail in details:
            for error in detail.get('errors', []):
                # Extract error type
                error_type = error.split(':')[0] if ':' in error else error
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        # Sort by frequency
        return [f"{err} ({count} occurrences)" 
                for err, count in sorted(error_counts.items(), 
                                        key=lambda x: x[1], 
                                        reverse=True)[:5]]
    
    def _get_common_warnings(self, details: List[Dict]) -> List[str]:
        """Extract common warning patterns"""
        warning_counts = {}
        for detail in details:
            for warning in detail.get('warnings', []):
                # Extract warning type
                warning_type = warning.split(':')[0] if ':' in warning else warning
                warning_counts[warning_type] = warning_counts.get(warning_type, 0) + 1
        
        # Sort by frequency
        return [f"{warn} ({count} occurrences)" 
                for warn, count in sorted(warning_counts.items(), 
                                         key=lambda x: x[1], 
                                         reverse=True)[:5]]
    
    def generate_report(self, validation_results: Dict) -> str:
        """Generate validation report"""
        report = []
        report.append("="*50)
        report.append("DATA VALIDATION REPORT")
        report.append("="*50)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        summary = validation_results['summary']
        report.append("SUMMARY:")
        report.append(f"  Total Pages Validated: {summary['total_validated']}")
        report.append(f"  Passed: {summary['passed']}")
        report.append(f"  Failed: {summary['failed']}")
        report.append(f"  Pass Rate: {summary['pass_rate']:.2f}%")
        report.append(f"  Total Warnings: {summary['total_warnings']}")
        report.append("")
        
        if summary['common_errors']:
            report.append("COMMON ERRORS:")
            for error in summary['common_errors']:
                report.append(f"  - {error}")
            report.append("")
        
        if summary['common_warnings']:
            report.append("COMMON WARNINGS:")
            for warning in summary['common_warnings']:
                report.append(f"  - {warning}")
            report.append("")
        
        # Failed pages details
        failed_pages = [d for d in validation_results['validation_details'] if not d['valid']]
        if failed_pages:
            report.append("FAILED PAGES:")
            for page in failed_pages[:10]:  # Limit to 10
                report.append(f"  URL: {page['url']}")
                for error in page['errors']:
                    report.append(f"    ERROR: {error}")
            if len(failed_pages) > 10:
                report.append(f"  ... and {len(failed_pages) - 10} more")
            report.append("")
        
        report.append("="*50)
        
        return "\n".join(report)


def main():
    """Test validation with sample data"""
    validator = DataValidator()
    
    # Sample data for testing
    sample_page = {
        'url': 'https://doc.sis.columbia.edu/test',
        'scraped_at': datetime.now().isoformat(),
        'title': 'Sample Documentation Page',
        'description': 'Test description',
        'content_sections': [
            {
                'type': 'div',
                'headings': [{'level': 'h2', 'text': 'Introduction'}],
                'paragraphs': ['This is a test paragraph with sufficient length.'],
                'lists': [{'type': 'ul', 'items': ['Item 1', 'Item 2']}]
            }
        ],
        'navigation_links': [
            {'href': '/page1', 'text': 'Page 1', 'is_internal': True},
            {'href': '/page2', 'text': 'Page 2', 'is_internal': True}
        ],
        'metadata': {'table_count': 2}
    }
    
    # Validate single page
    result = validator.validate_page(sample_page)
    print(f"Validation result: {result}")
    
    # Validate dataset
    dataset_result = validator.validate_dataset([sample_page])
    report = validator.generate_report(dataset_result)
    print(report)


if __name__ == "__main__":
    main()
