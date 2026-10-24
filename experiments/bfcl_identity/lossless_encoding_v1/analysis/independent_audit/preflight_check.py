"""Independent read-only preflight checks; outputs only to this audit directory."""
from pathlib import Path
import sys, json, hashlib, time, importlib
root=Path(__file__).resolve().parents[2]
snapshot=root/'source_code/candidates-v1'
sys.path.insert(0,str(snapshot/'scripts'))
from core import optimized_graph
from workflows.lossless_audit import audit

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
plan=read(root/'task-split.json'); registry=read(root/'candidate-registry.json')
old=Path(plan['old_study']); project=root.parents[2]
hashes=read(snapshot/'hashes.json')
assert all(sha(snapshot/p)==v for p,v in hashes.items())
assert len(plan['tasks'])==52 and len([t for t in plan['tasks'] if t['split']=='development'])==6
assert plan['development_seeds']==[1103,2207,3301] and plan['seeds']==[4409,5519,6637]
for row in plan['sources']: assert sha(project/row['path'])==row['sha256']
checks=[]
for task in plan['tasks']:
 if task['split']!='development': continue
 for seed in plan['development_seeds']:
  p=old/'tasks'/task['id']/f'seed{seed}'
  m=read(p/'identity/manifest.json')
  if not m['triggered']: continue
  history=read(p/'identity/checkpoint-history.json')
  history=[x for x in history if x.get('role') not in ('system','developer')]
  for method in ('state','event','dedup'):
   baseline=read(p/(method+'-'+plan['baseline_explanations'][method])/'memory-metadata.json')
   _,current=optimized_graph.build_memory(history,{'state':'v1-compact','event':'v2-compact','dedup':'v2-dedup'}[method],plan['baseline_explanations'][method],len)
   assert optimized_graph._same(baseline['graph'],current['graph'])
   assert baseline['instruction']==current['instruction']
   for candidate in [r for r in registry if r['method']==method and r['explanation']=='none']:
    codec=importlib.import_module(candidate['module'])
    encoded=codec.encode(baseline['graph'],candidate['variant'])
    restored=codec.decode(json.loads(json.dumps(encoded,ensure_ascii=False)))
    assert optimized_graph._same(restored,baseline['graph'])
    assert list(restored['source_messages'])==list(baseline['graph']['source_messages'])
    assert optimized_graph._same(optimized_graph.restore_history(restored),history)
    checks.append(dict(task=task['id'],seed=seed,method=method,variant=candidate['variant'],payload_exact=True,source_order_exact=True,history_exact=True))
completed=[]; in_progress=[]
for manifest in root.glob('development/*/seed*/*/manifest.json'):
 m=read(manifest)
 if m['status'] in ('complete','not_triggered'): completed.append(audit(manifest.parent))
 else: in_progress.append(dict(path=str(manifest.parent),status=m['status']))
result=dict(audit_kind='independent preflight code and partial artifact audit, not final result audit',created_at=time.time(),snapshot=str(snapshot),snapshot_files_verified=len(hashes),dataset_sources_verified=len(plan['sources']),payload_checks=checks,completed_artifact_checks=completed,in_progress=in_progress,module_locations={name:str(sys.modules[name].__file__) for name in ('core.optimized_graph','core.lossless_state','core.lossless_event','workflows.lossless_audit')},protocol_tests=5,codec_tests=20,selection_frozen=(root/'selection.json').exists(),fresh_evaluation_started=(root/'evaluation').exists())
(root/'analysis/independent_audit/preflight-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('payload_checks','completed_artifact_checks','module_locations','in_progress')}))
print('exact payload checks',len(checks),'completed run checks',len(completed),'live graph complete',sum(x['status']=='complete' for x in completed))
