"""Offline candidate: exact payload sharing across distinct result events.

Preserve every event, relation and known identifier occurrence inline.
This is a candidate for review, not an authorised paid experiment.
"""
from copy import deepcopy
from collections import defaultdict
from .subtree_share import _index,restore,render
from .g9_edit import _digest,render as render_full
from cs769.graphs.graph_memory_records import audit_record_graph

def share(graph,count):
 assert audit_record_graph(graph)['ok']
 nodes,expand,tree=_index(graph);events={n['id']:n for n in graph['evidence_view']['nodes']}
 protected={n['payload_node']for n in graph['record_layer']['nodes']if n['category']=='identifier_occurrence'}
 owner={};buckets=defaultdict(list);order={x:i for i,x in enumerate(nodes)}
 for f in graph['payload_layer']['fields']:
  if events[f['event_id']]['category']!='tool_result' or f['parse_fallback']is not None:continue
  for i in tree(f['root']):
   owner[i]=f['event_id'];n=nodes[i]
   if n['kind']not in ('object','array','scalar')or protected.intersection(tree(i)):continue
   value=expand(i)
   if len(value)>=100 and count(value)>=40:buckets[(n['kind'],value)].append(i)
 proposals=[]
 for (kind,value),ids in buckets.items():
  ids=sorted(set(ids),key=order.get)
  if len({owner[i]for i in ids})<2:continue
  est=(len(ids)-1)*count(value)-12*len(ids)
  if est>0:proposals.append((est,ids))
 proposals.sort(key=lambda x:(-x[0],order[x[1][0]]))
 used=set();groups=[];out=deepcopy(graph);dest={n['id']:n for n in out['payload_layer']['nodes']}
 for _,ids in proposals:
  avail=[i for i in ids if not used.intersection(tree(i))]
  if len({owner[i]for i in avail})<2:continue
  canonical=avail[0];base=tree(canonical);aliases=[]
  for root in avail[1:]:
   target=tree(root)
   if len(target)!=len(base):continue
   if not all(nodes[x]['kind']==nodes[y]['kind'] and nodes[x].get('text')==nodes[y].get('text')for x,y in zip(target,base)):continue
   aliases.append({'root':root,'leaf_refs':{x:y for x,y in zip(target,base)if 'text'in nodes[x]}})
  if len({owner[canonical]}|{owner[x['root']]for x in aliases})<2:continue
  for a in aliases:
   for old,new in a['leaf_refs'].items():dest[old].pop('text');dest[old]['text_ref']=new
   used.update(tree(a['root']))
  used.update(base);groups.append({'label':f'P{len(groups)}','canonical':canonical,'aliases':aliases})
 if not groups:raise ValueError('No positive-size exact subtree shared across distinct observations with ID protection')
 out['subtree_sharing']={'version':'g9-exact-observation-share-candidate-v1','original_graph_sha256':_digest(graph),'groups':groups}
 assert restore(out)==graph
 before=count(render_full(graph));after=count(render(out))
 if after>=before:raise ValueError('Reference overhead exceeds sharing benefit')
 details=[]
 for g in groups:
  roots=[g['canonical']]+[a['root']for a in g['aliases']]
  assert len({owner[i]for i in roots})>=2
  assert all(not protected.intersection(tree(i))for i in roots)
  details.append({'kind':nodes[g['canonical']]['kind'],'occurrences':len(roots),'events':sorted({owner[i]for i in roots}),
                  'value_tokens':count(expand(g['canonical'])),'root_ids':roots})
 return out,{'before_tokens':before,'after_tokens':after,'saved_tokens':before-after,'groups':details,
             'restores_source_graph_exactly':True,'known_identifier_nodes_kept_inline':True,'all_occurrences_and_relations_preserved':True,
             'task_safety_not_proven':True}
