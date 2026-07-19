from __future__ import annotations
import csv,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def main():
 failures=[]
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp); registry=root/'source_registry.csv'; fields=['source_id','marketplace','external_offer_id','canonical_url','normalized_brand','normalized_model']; rows=[{'source_id':'allegro:1','marketplace':'allegro','external_offer_id':'1','canonical_url':'https://allegro.pl/oferta/1','normalized_brand':'kinderkraft','normalized_model':'nebo'}]
  with registry.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
  req={'group_key':'kinderkraft|nebo','brand':'Kinderkraft','model':'NEBO','marketplace':'allegro','query':'Kinderkraft NEBO','existing_source_ids':['allegro:1'],'existing_external_offer_ids':['1'],'target_fields':[],'status':'prepared'}; (root/'search_request.json').write_text(json.dumps(req),encoding='utf-8'); loaded=json.loads((root/'search_request.json').read_text())
  if 'Kinderkraft' not in loaded['query'] or 'NEBO' not in loaded['query']: failures.append('query_missing_exact_model')
  for key in ('group_key','brand','model','marketplace','query','existing_source_ids','existing_external_offer_ids','target_fields','status'):
   if key not in loaded: failures.append('request_missing:'+key)
  result=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_targeted_model_search.py'),'--marketplace','amazon_test','--brand','Kinderkraft','--model','NEBO'],cwd=ROOT,capture_output=True,text=True)
  if result.returncode==0 or "Marketplace 'amazon_test' nie ma jeszcze adaptera targeted search." not in result.stdout: failures.append('unsupported_marketplace_error')
 if failures:print('FAIL\n'+'\n'.join(failures));return 1
 print('Result: OK');return 0
if __name__=='__main__':raise SystemExit(main())
