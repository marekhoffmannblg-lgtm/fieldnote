from __future__ import annotations
import argparse,csv,json,re
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; OUT=ROOT/'output/targeted_search'
FIELDS=("Marka","Model","Status","Rama","Koła","Udźwig","Regulacja oparcia","Auto-folding","Składanie jedną ręką","Waga","Wymiary po złożeniu","Siedzisko","Amortyzacja","Koła 360°","Hamulec","Budka XXL","Filtr UPF50+","Wodoodporna budka","Regulacja rączki","Wymiary oparcia / miejsce do spania","Akcesoria")
def slug(s):return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--marketplace',required=True);ap.add_argument('--brand',required=True);ap.add_argument('--model',required=True);ap.add_argument('--limit-pages',type=int,default=3);ap.add_argument('--force',action='store_true');a=ap.parse_args()
 if a.marketplace.lower()!='allegro':print(f"Marketplace '{a.marketplace}' nie ma jeszcze adaptera targeted search.");return 1
 key=f'{a.brand.lower()}|{a.model.lower()}'; d=OUT/f'{slug(a.brand)}__{slug(a.model)}'/a.marketplace.lower();d.mkdir(parents=True,exist_ok=True)
 state_path=ROOT/'output/model_groups'/f'{slug(a.brand)}__{slug(a.model)}'/'model_state.json'; target=[]
 if state_path.exists():
  state=json.loads(state_path.read_text(encoding='utf-8')); target=[field for field,item in state.get('fields',{}).items() if not item.get('locked') and item.get('status') in {'open','unclear','conflicting'} or (not item.get('locked') and item.get('status')=='confirmed')]
 else:
  coverage_path=ROOT/'output/model_coverage.json'
  if coverage_path.exists():
   coverage=next((r for r in json.loads(coverage_path.read_text(encoding='utf-8')) if r.get('group_key')==key),{}); target=[]
  if not target: target=list(FIELDS)
 registry=ROOT/'output/source_registry.csv'; existing=[]
 if registry.exists():
  with registry.open(encoding='utf-8',newline='') as f: existing=[r for r in csv.DictReader(f) if r.get('normalized_brand')==a.brand.lower() and r.get('normalized_model')==a.model.lower()]
 req={'group_key':key,'brand':a.brand,'model':a.model,'marketplace':a.marketplace.lower(),'query':f'{a.brand} {a.model}','created_at':datetime.now(timezone.utc).isoformat(),'status':'prepared','existing_source_ids':[r['source_id'] for r in existing],'existing_external_offer_ids':[r['external_offer_id'] for r in existing],'target_fields':target,'target_fields_count':len(target),'notes':[f'limit_pages={a.limit_pages}']}
 (d/'search_request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2),encoding='utf-8')
 with (d/'search_urls.csv').open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=['page','url','query']);w.writeheader();w.writerows({'page':i+1,'url':f'https://allegro.pl/listing?string={a.brand}+{a.model}&p={i+1}','query':req['query']} for i in range(a.limit_pages))
 print(f'prepared={d}');return 0
if __name__=='__main__':raise SystemExit(main())
