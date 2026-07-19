from __future__ import annotations
import json,tempfile
from pathlib import Path
def main():
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp); data=[('allegro:1001','allegro','nebo'),('amazon:ABC1','amazon','nebo'),('allegro:1002','allegro','trig 2'),('amazon:ABC2','amazon','trig 3'),('allegro:1003','allegro','nubi'),('amazon:ABC3','amazon','nubi 2')]
  groups={}
  for sid,market,model in data:
   key='kinderkraft|'+model; groups.setdefault(key,{'group_key':key,'brand':'Kinderkraft','model':model,'marketplaces':[],'sources':[]}); g=groups[key]; g['sources'].append({'source_id':sid,'marketplace':market});
   if market not in g['marketplaces']:g['marketplaces'].append(market)
  (root/'groups.json').write_text(json.dumps(groups),encoding='utf-8'); loaded=json.loads((root/'groups.json').read_text())
  failures=[]; nebo=loaded['kinderkraft|nebo']
  if set(nebo['marketplaces'])!={'allegro','amazon'}: failures.append('nebo_marketplaces')
  if len(nebo['sources'])!=2: failures.append('nebo_sources_deduplicated')
  if set(loaded)!={'kinderkraft|nebo','kinderkraft|trig 2','kinderkraft|trig 3','kinderkraft|nubi','kinderkraft|nubi 2'}: failures.append('generation_grouping')
  if any('amazon' not in s['source_id'] and 'allegro' not in s['source_id'] for s in nebo['sources']): failures.append('source_provenance')
  if failures:print('FAIL\n'+'\n'.join(failures));return 1
 print('Result: OK');return 0
if __name__=='__main__':raise SystemExit(main())
