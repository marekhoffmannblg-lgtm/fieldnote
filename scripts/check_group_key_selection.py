from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def main():
    failures=[]
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); groups=root/'groups'; groups.mkdir()
        for folder,key in [('arbitrary-nebo-name','kinderkraft|nebo'),('000_tik','kinderkraft|tik'),('trig-folder','kinderkraft|trig 3')]:
            d=groups/folder; d.mkdir(); (d/'group.json').write_text(json.dumps({'group_key':key,'brand':'Kinderkraft','model':key.split('|')[1],'sources':[]}),encoding='utf-8')
        loaded=[json.loads(p.read_text()) for p in groups.glob('*/group.json')]
        chosen=[p for p in groups.iterdir() if json.loads((p/'group.json').read_text()).get('group_key')=='kinderkraft|nebo']
        if len(chosen)!=1 or chosen[0].name!='arbitrary-nebo-name': failures.append('group_key_selection')
        if any(json.loads((p/'group.json').read_text()).get('group_key')=='kinderkraft|nebo' for p in groups.iterdir() if p.name!='arbitrary-nebo-name'): failures.append('other_groups_selected')
        if any(p.name.startswith('000_') and json.loads((p/'group.json').read_text()).get('group_key')=='kinderkraft|nebo' for p in groups.iterdir()): failures.append('prefix_dependency')
        expected={groups/'arbitrary-nebo-name'/'group.json', groups/'000_tik'/'group.json', groups/'trig-folder'/'group.json'}
        if set(groups.glob('*/*')) != expected: failures.append('nested_folder_created')
    result=subprocess.run([sys.executable,str(ROOT/'scripts/extract_model_facts_cascade.py'),'--group-key','missing|model','--dry-run'],cwd=ROOT,capture_output=True,text=True)
    if result.returncode==0 or 'Nie znaleziono group_key' not in result.stdout: failures.append('missing_key_error')
    if failures: print('FAIL\n'+'\n'.join(failures)); return 1
    print('Result: OK'); return 0
if __name__=='__main__': raise SystemExit(main())
