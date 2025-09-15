import json, requests, re
D=json.load(open('data/sample_output.json','r',encoding='utf-8'))
for r in D:
    if not (r.get('course_code') and r.get('section') and r.get('subject')):
        print('BAD', r.get('detail_url'))
        try:
            html = requests.get(r.get('detail_url'), timeout=10).text
            print('H2', re.findall(r"<h2>(.*?)</h2>", html, flags=re.I|re.S)[:1])
        except Exception as e:
            print('fetch_err', e)
        break
