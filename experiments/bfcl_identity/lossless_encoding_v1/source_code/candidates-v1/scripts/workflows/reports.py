"""Render renamed reading copies without changing frozen experiment artifacts."""
import json,re,hashlib
from pathlib import Path
from core.research_modes import LABELS,SHORT_LABELS
ROOT=Path(__file__).resolve().parents[2]/'experiments/bfcl_identity'
SOURCES={'baseline': 'qwen27b_experiment', 'event_graph_dedup_offline':'v2_provenance_dedup_probe', 'event_graph_dedup_eval':'qwen27b_dedup_eval'}
def main():
    out=ROOT/'reports';out.mkdir(exist_ok=True)
    aliases={'Mem Identity':LABELS['identity'],'V1-Compact':LABELS['v1-compact'],'V2-Compact':LABELS['v2-compact'],**LABELS,'V2 来源关系无损去重':LABELS['v2-dedup'],'V2 无损来源去重':LABELS['v2-dedup'],'原 V2':'Event Graph','Identity/V2':'Identity/Event Graph'}
    pattern=re.compile('|'.join(re.escape(k) for k in sorted(aliases,key=len,reverse=True)))
    sources={}
    for name,folder in SOURCES.items():
        src=ROOT/folder/'report.txt';raw=src.read_text()
        (out/(name+'.txt')).write_text('展示名称已统一；数值未改变。原始来源：'+folder+'/report.txt\n\n'+pattern.sub(lambda m:aliases[m.group()],raw))
        sources[folder+'/report.txt']=hashlib.sha256(src.read_bytes()).hexdigest()
    (out/'names.json').write_text(json.dumps({'labels':LABELS,'short_labels':SHORT_LABELS,'source_sha256':sources},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
