import json
from src.scraper import parse_subject_text_page, _DEMO_SAMPLE
sections = parse_subject_text_page(_DEMO_SAMPLE, 'ACCT', 'Fall 2025')
print(f'Parsed {len(sections)} demo sections')
with open('data/sample_output.json','w', encoding='utf-8') as f:
    json.dump(sections, f, ensure_ascii=False, indent=2)
print('Wrote demo sample to data/sample_output.json')
