"""Read-only mechanical audit of run evidence, separate from scoring claims."""
import argparse
import hashlib
import json
from pathlib import Path
from workflows.work1000_task import all_paired
from workflows.lossless_controller import read, write


def audit(path):
    m=read(path/'manifest.json')
    assert m['status'] in ('complete','not_triggered')
    launch=read(path/'launch.json')
    if m['status']=='not_triggered':
        assert not read(Path(m['identity'])/'manifest.json')['triggered']
        return dict(path=str(path),status='not_triggered',audit='pass')
    tape=read(path/'api.json')
    accounting=read(path/'accounting.json')
    native=[json.loads(line) for line in (path/'native.jsonl').read_text().splitlines()]
    requests={r['index']:r for r in native if r['event']=='request'}
    responses={r['index']:r for r in native if r['event']=='response'}
    for a in accounting:
        i=a['index']
        assert a['input_tokens']==responses[i]['response']['usage']['prompt_tokens']
        assert a['working_tokens']==a['input_tokens']-a['fixed_tokens']
        assert a['seed']==m['seed']+i*1000003
        for k,v in m['sampling'].items():
            assert requests[i]['request'][k]==v
    boundary=m.get('trigger_index')
    if m['method']=='identity':
        eligible=[a['index'] for a in accounting if a['working_tokens']>1000
                  and all_paired(tape[a['index']]['request']['input'])]
        assert boundary==(eligible[0] if eligible else None)
    else:
        source=Path(m['identity'])
        sm=read(source/'manifest.json')
        st=read(source/'api.json')
        assert boundary==sm['trigger_index']
        for k in ('task','category','seed','sampling'):
            assert m[k]==sm[k]
        for i in range(boundary):
            for key in ('request','response'):
                assert tape[i][key]==st[i][key]
        history=read(path/'checkpoint-history.json')
        assert history==st[boundary]['request']['input'] and all_paired(history)
        initial=tape[boundary]['request']['input']
        assert initial[-1]==dict(role='user',content=(path/'memory.txt').read_text())
        assert all(item.get('role') in ('system','developer') for item in initial[:-1])
        for row in tape[boundary:]:
            assert row['request']['input'][:len(initial)]==initial
    return dict(path=str(path),status=m['status'],audit='pass',triggered=m['triggered'],
                passed=m['passed'],source_snapshot=launch['source_snapshot'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[]
    paths=sorted(args.root.glob('tasks/*/seed*/*/manifest.json'))
    paths+=sorted(args.root.glob('development/*/seed*/*/manifest.json'))
    paths+=sorted(args.root.glob('evaluation/*/seed*/*/manifest.json'))
    for manifest in paths:
        try:
            rows.append(audit(manifest.parent))
        except Exception as error:
            rows.append(dict(path=str(manifest.parent),audit='fail',error=repr(error)))
    snapshots={r['source_snapshot'] for r in rows if 'source_snapshot' in r}
    hashes={}
    for snapshot in snapshots:
        directory=Path(snapshot)
        hashes[snapshot]=all(hashlib.sha256((directory/p).read_bytes()).hexdigest()==h
                             for p,h in read(directory/'hashes.json').items())
    result=dict(counts={status:sum(r['audit']==status for r in rows) for status in ('pass','fail')},
                snapshot_hashes=hashes,rows=rows)
    write(args.output,result)
    print(json.dumps(result['counts']))
    if result['counts']['fail'] or not all(hashes.values()):
        raise SystemExit(1)


if __name__=='__main__':
    main()
