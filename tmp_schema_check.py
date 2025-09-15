import json, re
from src.validators import sync_labels, validate_course
from src.transformers import merge_days
import sys
p='data/sample_output.json'
try:
    data=json.load(open(p,'r',encoding='utf-8'))
except Exception as e:
    print('LOAD_FAIL', e); sys.exit(1)
print('records', len(data))
CANON=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
missing_keys=0; bad_days=0; ghost=0; bad_loc=0; sync_bad=0
for r in data:
    # Required keys present
    for k in ['days','start_hhmm','end_hhmm','start_label','end_label','location','instructor','course_code','section','subject']:
        if k not in r:
            missing_keys+=1; break
    # Days canonical
    if any(d not in CANON for d in r.get('days') or []):
        bad_days+=1
    # Ghost 00:10
    if r.get('start_label')=='00:10' or r.get('end_label')=='00:10':
        ghost+=1
    # TBA building rule
    loc=r.get('location') or {}
    if (loc.get('building')=='To be announced' and loc.get('room')):
        bad_loc+=1
    # sync labels
    if not sync_labels(r.get('start_hhmm'), r.get('start_label')):
        sync_bad+=1
    if not sync_labels(r.get('end_hhmm'), r.get('end_label')):
        sync_bad+=1
print('missing_keys', missing_keys, 'bad_days', bad_days, 'ghost_0010', ghost, 'tba_room', bad_loc, 'sync_bad', sync_bad)
# quick issues count
issues=0
for r in data:
    issues += len(validate_course(r))
print('validate_issues', issues)
print('sample_row_keys', list(data[0].keys()) if data else [])
