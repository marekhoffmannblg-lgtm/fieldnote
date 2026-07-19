from __future__ import annotations
import csv,subprocess,sys
import tempfile
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
from build_model_benchmark import normalize_evidence_items
def main():
 r=subprocess.run([sys.executable,str(ROOT/'scripts/build_model_benchmark.py')],cwd=ROOT,capture_output=True,text=True); failures=[]
 with tempfile.TemporaryDirectory() as temp:
  path=Path(temp)/'evidence.json'; path.write_text(json.dumps(["W zestawie: torba transportowa, pasek na ramię",{"source_id":"allegro:1","evidence":"Akcesoria: folia przeciwdeszczowa, uchwyt na kubek"},None]),encoding='utf-8')
  mixed=normalize_evidence_items(json.loads(path.read_text(encoding='utf-8')),'tak')
  if len(mixed)!=2 or mixed[0]['value']!='tak' or mixed[1]['source_id']!='allegro:1': failures.append('mixed_evidence')
  for value,expected in [("W zestawie: torba",1),(None,0),([],0),({"evidence":"dict"},1)]:
   if len(normalize_evidence_items(value,'tak'))!=expected: failures.append('evidence_shape')
 for name in ('model_benchmark.csv','model_benchmark_sources.csv','model_benchmark_quality.json'):
  if not (ROOT/'output'/name).exists(): failures.append('missing:'+name)
 path=ROOT/'output/model_benchmark.csv'
 if path.exists():
  with path.open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
  keys=[row.get('group_key') for row in rows]
  if len(keys)!=len(set(keys)): failures.append('duplicate_model_rows')
  if any(not row.get('group_key') for row in rows): failures.append('empty_group_key')
 if r.returncode: failures.append('builder_failed')
 if failures: print('FAIL\n'+'\n'.join(failures)); return 1
 print('Result: OK'); return 0
if __name__=='__main__': raise SystemExit(main())
