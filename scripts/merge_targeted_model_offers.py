from __future__ import annotations
import argparse,csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; REG=ROOT/'output/source_registry.csv'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--marketplace',required=True);ap.add_argument('--brand',required=True);ap.add_argument('--model',required=True);ap.add_argument('--input-csv',required=True);ap.add_argument('--force',action='store_true');a=ap.parse_args()
 if a.marketplace.lower()!='allegro':print(f"Marketplace '{a.marketplace}' nie ma jeszcze adaptera targeted search.");return 1
 rows=[]
 if REG.exists():
  with REG.open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
 seen={(r.get('source_id'),r.get('marketplace'),r.get('external_offer_id'),r.get('canonical_url')) for r in rows}; added=0
 with Path(a.input_csv).open(encoding='utf-8',newline='') as f:
  for r in csv.DictReader(f):
   oid=r.get('external_offer_id') or r.get('offer_id',''); record={'source_id':f'{a.marketplace.lower()}:{oid}','marketplace':a.marketplace.lower(),'source_type':'marketplace_offer','external_offer_id':oid,'source_url':r.get('source_url',r.get('normalized_url','')),'canonical_url':r.get('canonical_url',r.get('normalized_url','')),'brand':a.brand,'normalized_brand':a.brand.lower(),'model':a.model,'normalized_model':a.model.lower(),'title':r.get('title',''),'seller_name':r.get('seller_name',''),'seller_rating':r.get('seller_rating',''),'country':r.get('country','PL'),'language':r.get('language','pl'),'fetched_at':r.get('fetched_at',''),'offer_sections_path':r.get('offer_sections_path',''),'seller_info_path':r.get('seller_info_path',''),'product_images_path':r.get('product_images_path',''),'quality_score':r.get('quality_score','0'),'quality_reasons':r.get('quality_reasons',''),'eligible_for_grouping':'true','warnings':''}
   key=(record['source_id'],record['marketplace'],record['external_offer_id'],record['canonical_url'])
   if not oid or key in seen:continue
   rows.append(record);seen.add(key);added+=1
 if rows:
  fields=list(rows[0]);
  with REG.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 print(f'added={added}');return 0
if __name__=='__main__':raise SystemExit(main())
