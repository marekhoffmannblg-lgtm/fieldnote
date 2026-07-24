from __future__ import annotations
import json, tempfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT/'scripts'))
from fetch_targeted_model_offers import extract_offers
def main():
 with tempfile.TemporaryDirectory() as temp:
  html=''.join([
   '<a href="https://allegro.pl/produkt/kinderkraft-nebo?offerId=18405722631">Kinderkraft NEBO wózek</a>',
   '<a href="https://allegro.pl/events/clicks?redirect=https%3A%2F%2Fallegro.pl%2Foferta%2Fkinderkraft-nebo-18405722631">Kinderkraft NEBO wózek</a>',
   '<a href="https://allegro.pl/produkt/kinderkraft-nebo?offerId=18313010667">Kinderkraft NEBO wózek</a>',
   ''.join(f'<a href="https://allegro.pl/oferta/kinderkraft-nea-{i}">{"Kinderkraft NEA wózek"}</a>' for i in range(10000001,10000008)),
   '<h2>Filtry</h2><a href="/kategoria/wozki">Wózki</a>'
  ])
  accepted,rejected=extract_offers(html,'Kinderkraft','NEBO','stroller'); ids={x['offer_id'] for x in accepted+rejected if x['offer_id']}; failures=[]
  if len(ids)!=9: failures.append(f'unique_ids:{len(ids)}')
  if len(accepted)!=2: failures.append(f'accepted:{len(accepted)}')
  if len(rejected)!=7: failures.append(f'rejected:{len(rejected)}')
  if len(ids) != len(accepted) + len(rejected): failures.append('counter_invariant')
  if any(not x['accepted'] for x in accepted): failures.append('accepted_flag_false')
  if any('/events/clicks' in x['canonical_url'] for x in accepted): failures.append('tracking_canonical_url')
  if any(not x['canonical_url'].rstrip('/').split('-')[-1].isdigit() for x in accepted): failures.append('canonical_offer_id')
  if any('NEA' in x['title'] and x['accepted'] for x in rejected): failures.append('nea_accepted')
  if len({x['offer_id'] for x in accepted})!=2: failures.append('tracking_dedup')
 if failures: print('FAIL\n'+'\n'.join(failures)); return 1
 print('Result: OK'); return 0
if __name__=='__main__': raise SystemExit(main())
