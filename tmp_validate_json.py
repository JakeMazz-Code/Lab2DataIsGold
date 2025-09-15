import json
from src.validators import validate_course
with open('data/sample_output.json','r',encoding='utf-8') as f:
    data = json.load(f)
issues = []
for r in data:
    issues.extend(validate_course(r))
print(f'sections={len(data)} issues={len(issues)}')
from collections import Counter
print(Counter((i['level'], i['field']) for i in issues))
