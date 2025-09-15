import json
from collections import Counter
from src.validators import validate_course
D=json.load(open('data/sample_output.json','r',encoding='utf-8'))
C=Counter()
for r in D:
    for i in validate_course(r):
        C[(i['level'], i['field'])]+=1
print(C)
