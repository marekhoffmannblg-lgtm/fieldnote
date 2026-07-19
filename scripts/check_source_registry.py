from __future__ import annotations
import csv,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; OUT=ROOT/'output'
def main():
 failures=[]; jp=OUT/'source_registry.jsonl'; cp=OUT/'source_registry.csv'
 if not jp.exists() or not cp.exists(): failures.append('registry_outputs_missing'); print('FAIL\n'+'\n'.join(failures)); return 1
 records=[]
 for line in jp.read_text(encoding='utf-8').splitlines():
  try: records.append(json.loads(line))
  except json.JSONDecodeError: failures.append('invalid_jsonl')
 with cp.open(encoding='utf-8',newline='') as f: csv_rows=list(csv.DictReader(f))
 if not records: failures.append('no_records')
 if len(records)!=len(csv_rows): failures.append('jsonl_csv_count_mismatch')
 ids=[]
 required=('source_id','marketplace','source_type','source_url','normalized_brand','normalized_model','eligible_for_grouping')
 for r in records:
  if any(k not in r or r.get(k) in (None, '') for k in required if k != 'eligible_for_grouping'): failures.append('required_field_missing')
  marketplace=str(r.get('marketplace',''))
  if marketplace not in {'allegro','manufacturer'}: failures.append('unsupported_marketplace')
  if marketplace != marketplace.lower(): failures.append('marketplace_not_lowercase')
  if marketplace=='allegro' and r.get('source_id')!=f"allegro:{r.get('external_offer_id')}": failures.append('invalid_source_id')
  if marketplace=='manufacturer' and not str(r.get('source_id','')).startswith('manufacturer:'): failures.append('invalid_source_id')
  if r.get('eligible_for_grouping') and (not r.get('normalized_brand') or not r.get('normalized_model')): failures.append('uncertain_record_eligible')
  if r.get('eligible_for_grouping') and marketplace=='allegro' and not (ROOT/r.get('offer_sections_path','')).exists(): failures.append('offer_sections_missing')
  if r.get('eligible_for_grouping') and marketplace=='manufacturer' and not (ROOT/r.get('content_path','')).exists(): failures.append('manufacturer_content_missing')
  ids.append(r.get('source_id'))
 if len(ids)!=len(set(ids)): failures.append('duplicate_source_ids')
 if failures: print('FAIL\n'+'\n'.join(sorted(set(failures)))); return 1
 print('Result: OK'); return 0
if __name__=='__main__': raise SystemExit(main())
