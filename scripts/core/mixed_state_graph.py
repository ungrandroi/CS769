"""Separately versioned mixed-domain State graph; legacy GraphMemory is unchanged."""
from copy import deepcopy
from core.state_transition_graph import GraphMemory, plain
from core.mixed_observations import REGISTRY_VERSION, domain_effect, registry

ADAPTER_VERSION = 'mixed-state-graph-1'
SEMANTIC_SCHEMA_VERSION = 'mixed-state-transition-1'


def _same(a, b):
    if type(a) is not type(b): return False
    if isinstance(a,dict): return a.keys()==b.keys() and all(_same(a[k],b[k]) for k in a)
    if isinstance(a,list): return len(a)==len(b) and all(_same(x,y) for x,y in zip(a,b))
    return a==b


class MixedStateGraph(GraphMemory):
    """Filesystem state plus namespaced domain entities and dated observations.

    Every node includes domain_state, including s0. Active fields have current
    evidence; versions retain retired values and repeated confirmations. This is
    a semantic extension, not a change to any historical codec or builder.
    """
    def build(self, messages):
        source = plain(messages)
        seen = set()
        for message in source:
            calls = message.get('tool_calls') or []
            ids = [call['id'] for call in calls]
            if message.get('type')=='function_call': ids.append(message['call_id'])
            for identity in ids:
                if identity in seen: raise ValueError(f'Duplicate call ID: {identity}')
                seen.add(identity)
        self.domain_state = {'entities':{}, 'observations':[]}
        graph = super().build(source)
        coverage = {}
        for edge in graph['edges']:
            domain = coverage.setdefault(edge['domain'], {})
            tool = domain.setdefault(edge['tool'], {'calls':0, 'coverage':{}, 'outcomes':{}})
            tool['calls'] += 1
            for target,value in [('coverage',edge['coverage']),('outcomes',edge['status'])]:
                tool[target][value] = tool[target].get(value,0)+1
        graph.update(semantic_schema_version=SEMANTIC_SCHEMA_VERSION, adapter_version=ADAPTER_VERSION,
                     registry_version=REGISTRY_VERSION, domain_coverage=coverage,
                     semantic_adapter=ADAPTER_VERSION, semantic_registry=REGISTRY_VERSION,
                     semantic_contract_sha256=deepcopy(registry()['source_sha256']),
                     representation='mixed_domain_state_nodes_tool_edges')
        return graph

    def _node(self, description, evidence):
        node = super()._node(description, evidence)
        node['state']['domain_state'] = deepcopy(self.domain_state)
        return node

    def _retire_fields(self, entity, fields, step, reason):
        record = self.domain_state['entities'][entity]
        names = list(record['fields']) if fields is None else fields
        for field in names:
            if field not in record['fields']: continue
            record['versions'][field][-1]['retired_at'] = step
            record['versions'][field][-1]['retired_reason'] = reason
            del record['fields'][field]
            record['evidence'].pop(field, None)

    def _apply_domain_effect(self, effect, refs, step, edge_id):
        entities = self.domain_state['entities']
        for invalid in effect['invalidations']:
            for identity, record in list(entities.items()):
                if invalid.get('entity') is not None and identity!=invalid['entity']: continue
                if invalid.get('domain') is not None and record['domain']!=invalid['domain']: continue
                self._retire_fields(identity, invalid.get('fields'), step, invalid['reason'])
        if effect['operation'].get('kind')=='delete_latest_message':
            receiver = effect['operation']['receiver_id']
            for identity, record in list(entities.items()):
                if record['domain']=='MessageAPI' and record['entity_type']=='message' and record['fields'].get('receiver_id')==receiver:
                    self._retire_fields(identity, ['exists'], step, 'receiver_deletion_identity_undisclosed')
        for update in effect['updates']:
            identity = update['entity']
            domain,kind,local_id = identity.split(':',2)
            record = entities.setdefault(identity, {'domain':domain, 'entity_type':kind, 'local_id':local_id,
                                                      'fields':{}, 'evidence':{}, 'versions':{}})
            for field,value in update['fields'].items():
                confirmations = {'event':edge_id, 'at_step':step, 'messages':refs.copy()}
                history = record['versions'].setdefault(field, [])
                if field in record['fields'] and _same(record['fields'][field],value):
                    history[-1]['confirmations'].append(confirmations)
                    record['evidence'][field] = list(dict.fromkeys(record['evidence'][field]+refs))
                    continue
                if field in record['fields']:
                    self._retire_fields(identity,[field],step,'superseded_by_observation')
                history.append({'version':len(history)+1, 'value':deepcopy(value), 'valid_from':step,
                                'retired_at':None, 'retired_reason':None, 'confirmations':[confirmations]})
                record['fields'][field] = deepcopy(value)
                record['evidence'][field] = refs.copy()
        for observation in effect['observations']:
            self.domain_state['observations'].append({**deepcopy(observation),'domain':effect['domain'],
                                                     'at_step':step,'event':edge_id,'evidence':refs.copy()})

    def _execute(self, call, raw, output_ref):
        effect = domain_effect(call['tool'],call['arguments'],raw)
        refs = [call['call_evidence'], output_ref]
        domain = effect['domain']
        edge_id = f'e{len(self.graph["edges"])}'
        step = len(self.graph['edges'])+1
        if domain=='GorillaFileSystem' and effect['status']=='success':
            delegated = {**call, 'tool':effect['method']}
            super()._execute(delegated,raw,output_ref)
            edge = self.graph['edges'][-1]
            edge.update(tool=call['tool'], domain=domain, coverage=effect['coverage'],
                        outcome_basis=effect['basis'], status=effect['status'])
            return
        # New status handling also prevents executor error text from becoming a
        # successful filesystem mutation. Known external domains never clear FS.
        scope = self.cwd['location_id']
        reset_fs = any(item.get('domain') in (None,'GorillaFileSystem') and item.get('entity') is None
                       and item.get('fields') is None for item in effect['invalidations'])
        if reset_fs:
            self._invalidate_location(None, refs)
            self.cwd = {'location_id':self._location(None,f'unknown_after_{edge_id}'),
                        'value':None,'evidence':refs.copy()}
        self._apply_domain_effect(effect,refs,step,edge_id)
        edge = {'id':edge_id,'from':self.graph['nodes'][-1]['id'],**call,
                'output_evidence':output_ref,'output_raw':raw,'output':deepcopy(effect['parsed_output']),
                'status':effect['status'],'error':deepcopy(effect['error']),
                'status_basis':'method-aware visible return; not task completion',
                'domain':domain,'coverage':effect['coverage'],'outcome_basis':effect['basis'],
                'sequence':len(self.graph['edges']),'goal_refs':self.goals.copy()}
        self.observations.append({'edge':edge_id,'tool':call['tool'],'location_id':scope,
                                  'domain':domain,'evidence':refs.copy(),'status':effect['status']})
        node = self._node(f"{domain}.{effect['method']}: {effect['status']}; {effect['coverage']}",refs)
        edge['to'] = node['id']
        self.graph['edges'].append(edge)
