from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def main():
 failures=[]; states=list((ROOT/'output/model_groups').glob('*/model_state.json'))
 if not states: print('Result: OK'); return 0
 for path in states:
  state=json.loads(path.read_text(encoding='utf-8')); fields=state.get('fields',{}); locked={k:v for k,v in fields.items() if v.get('locked')}
  processed=state.get('processed_source_ids',state.get('processed_offer_ids',[]))
  if not isinstance(processed,list): failures.append('processed_ids_not_list')
  for name,item in locked.items():
   if item.get('value')=='X': failures.append('locked_x:'+name)
  prompts=list((path.parent/'prompts').glob('*.txt'))
  if prompts and locked:
   text=prompts[-1].read_text(encoding='utf-8')
   import re
   match=re.search(r'target_fields:\s*(\[[^\n]+\])',text)
   target=json.loads(match.group(1)) if match else []
   for name in locked:
    if name in target: failures.append('locked_field_in_target:'+name)
 if failures:print('FAIL\n'+'\n'.join(sorted(set(failures))));return 1
 print('Result: OK');return 0
if __name__=='__main__':raise SystemExit(main())
