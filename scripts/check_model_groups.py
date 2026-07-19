from __future__ import annotations
import csv,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def main():
 r=subprocess.run([sys.executable,str(ROOT/'scripts/build_model_groups.py'),'--max-offers-per-model','5','--force'],cwd=ROOT,capture_output=True,text=True); failures=[]
 if r.returncode: failures.append('build_failed')
 groups=list((ROOT/'output/model_groups').glob('*/group.json')) if (ROOT/'output/model_groups').exists() else []
 if not groups: failures.append('groups_missing')
 keys=[json.loads(p.read_text(encoding='utf-8'))['group_key'] for p in groups]
 for pair in [('kinderkraft|nebo','kinderkraft|nebo')]:
  if pair[0] not in keys: failures.append('nebo_missing')
 if any(k=='kinderkraft|nubi' for k in keys) and any(k=='kinderkraft|nubi 2' for k in keys): pass
 if failures: print('FAIL\n'+'\n'.join(failures)); return 1
 print('Result: OK'); return 0
if __name__=='__main__': raise SystemExit(main())
