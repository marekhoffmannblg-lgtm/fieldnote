from __future__ import annotations
import sys
import tempfile
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'scripts'))
from extract_model_facts_cascade import normalize_evidence_items, validate_field_result
def main():
 failures=[]
 with tempfile.TemporaryDirectory() as temp:
  path=Path(temp)/'evidence.json'
  path.write_text(json.dumps(["W zestawie: torba transportowa, pasek na ramię", {"source_id":"allegro:1","evidence":"Akcesoria: folia przeciwdeszczowa, uchwyt na kubek"}, None]), encoding='utf-8')
  loaded=json.loads(path.read_text(encoding='utf-8'))
  mixed=normalize_evidence_items(loaded, 'tak')
  if len(mixed)!=2 or mixed[0]['value']!='tak' or mixed[1]['source_id']!='allegro:1': failures.append('mixed_evidence_normalization')
  if normalize_evidence_items(None) or normalize_evidence_items([]): failures.append('empty_evidence_normalization')
  if normalize_evidence_items('W zestawie: torba')[0]['evidence']!='W zestawie: torba': failures.append('string_evidence_normalization')
 rejected=[('Auto-folding','tak','Brak informacji o automatycznym składaniu'),('Auto-folding','tak','szybki system składania'),('Koła 360°','tak','Koła EVA odporne na przebicia'),('Budka XXL','tak','budka z UPF50+'),('Regulacja rączki','tak','eko-skóra na rączce'),('Wymiary oparcia / miejsce do spania','34 cm','pozycja leżąca'),('Status','do 22 kg','do 22 kg'),('Akcesoria','tak','Akcesoria w zestawie')]
 for field,value,evidence in rejected:
  if validate_field_result(field,{'value':value,'status':'confirmed','confidence':'high','evidence':evidence})['value']!='X':failures.append('accepted_invalid:'+field)
 accepted=[('Akcesoria','tak','W zestawie: torba transportowa, pasek na ramię'),('Akcesoria','folia przeciwdeszczowa, uchwyt na kubek','Akcesoria: folia przeciwdeszczowa, uchwyt na kubek'),('Koła 360°','360°','Przednie koła obracają się o 360°'),('Auto-folding','automatyczne składanie','Automatyczne składanie jednym przyciskiem')]
 for field,value,evidence in accepted:
  result=validate_field_result(field,{'value':value,'status':'confirmed','confidence':'high','evidence':evidence})
  if result['value']=='X' or (field=='Akcesoria' and result['value']=='tak'):failures.append('rejected_valid:'+field)
 if failures:print('FAIL\n'+'\n'.join(failures));return 1
 print('Result: OK');return 0
if __name__=='__main__':raise SystemExit(main())
