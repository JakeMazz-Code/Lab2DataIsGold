import json
D=json.load(open('data/sample_output.json','r',encoding='utf-8'))
miss=[]
for r in D:
    ok = bool(r.get('course_code')) and bool(r.get('section')) and bool(r.get('subject'))
    if not ok:
        miss.append((r.get('subject'), r.get('number'), r.get('section'), r.get('course_code')))
print('invalid_count', len(miss))
print(miss[:10])
