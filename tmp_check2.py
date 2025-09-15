import json
from src.validators import validate_course, sync_labels
D=json.load(open('data/sample_output.json','r',encoding='utf-8'))
print('records', len(D))
print('invalid_by_validator', sum(1 for r in D if any(i['level']=='error' and i['field']=='record' for i in validate_course(r))))
print('ghost_0010', sum(1 for r in D if r.get('start_label')=='00:10' or r.get('end_label')=='00:10'))
print('label_mismatch_warns_start', sum(1 for r in D if not sync_labels(r.get('start_hhmm'), r.get('start_label'))))
print('label_mismatch_warns_end', sum(1 for r in D if not sync_labels(r.get('end_hhmm'), r.get('end_label'))))
