"""A separate, visible-evidence-only mixed-domain Event Graph adapter.

The historical GraphMemoryV2 is unchanged. Event Graph and Event Graph-Dedup
share this semantic builder; any provenance deduplication is a delivery codec.
Known non-filesystem APIs never invalidate filesystem facts. All unsupported
coverage and conservative invalidations remain explicit in the returned graph.
"""
from copy import deepcopy
import json

from core.event_graph import GraphMemoryV2
from core.mixed_observations import REGISTRY_VERSION, domain_effect, entity_id
from core.state_transition_graph import FS_READS, FS_WRITES

ADAPTER_VERSION = 'bfcl-mixed-event-1'
SEMANTIC_SCHEMA_VERSION = 'mixed-object-fact-event-1'
FS_DOMAIN = 'GorillaFileSystem'
DOMAINS = {FS_DOMAIN, 'TwitterAPI', 'MessageAPI', 'TicketAPI', 'MathAPI'}


def _same(left, right):
    """Do not conflate true/1 or integers/floats in observed domain values."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


class MixedEventGraph(GraphMemoryV2):
    """Versioned domain entities plus one execution event per paired return."""

    def build(self, messages):
        graph = super().build(messages)
        graph.update(semantic_schema_version=SEMANTIC_SCHEMA_VERSION,
                     adapter_version=ADAPTER_VERSION, registry_version=REGISTRY_VERSION,
                     rule_version=ADAPTER_VERSION)
        coverage = {}
        for node in graph['nodes']:
            if node['category'] != 'event':
                continue
            domain = coverage.setdefault(node['domain'], {})
            tool = domain.setdefault(node['tool'], {'calls': 0, 'coverage': {}, 'outcomes': {}})
            tool['calls'] += 1
            for target, value in [('coverage', node['coverage']), ('outcomes', node['status'])]:
                tool[target][value] = tool[target].get(value, 0) + 1
        # Only actually observed calls: no unavailable/excluded tool catalog.
        graph['domain_coverage'] = coverage
        self.validate()
        return graph

    def _entity(self, identity=None, origin='observed_object'):
        if identity is not None and identity in self.nodes:
            return identity
        identity = super()._entity(identity, origin)
        node = self.nodes[identity]
        parts = identity.split(':', 2)
        if len(parts) == 3 and parts[0] in DOMAINS:
            domain, kind, spelling = parts
            local_id = json.loads(spelling)
            if type(local_id) not in (str, int):
                raise ValueError('Non-scalar domain entity identity')
        else:
            domain = FS_DOMAIN
            kind = ('session' if identity == 'session' else
                    'location' if 'location' in origin else 'object')
            local_id = identity
        node.update(domain=domain, entity_type=kind, domain_id=local_id)
        return identity

    def _fact(self, subject, predicate, value, key=None, basis=None, derived_from=()):
        old = self._get(subject, predicate, key)
        # The inherited builder uses Python ==; retain its provenance machinery
        # while handling type-sensitive values that Python considers equivalent.
        typed_change = old is not None and old['value'] == value and not _same(old['value'], value)
        if typed_change:
            self._retire(old, 'superseded')
        fact = super()._fact(subject, predicate, value, key, basis, derived_from)
        if typed_change:
            self._edge(fact['id'], 'supersedes', old['id'])
        subject_node = self.nodes[subject]
        fact.update(domain=subject_node.get('domain', FS_DOMAIN),
                    fact_scope='observation' if predicate.startswith('observation.') else 'state')
        return fact

    def _invalidate(self, domain, entity=None, fields=None, reason='unmodeled_effect'):
        names = None if fields is None else {'attribute.' + field for field in fields}
        for identity in list(self.active.values()):
            fact = self.nodes[identity]
            if fact.get('fact_scope') == 'observation':
                continue  # An earlier observed result remains historically true.
            if domain is not None and fact.get('domain', FS_DOMAIN) != domain:
                continue
            if entity is not None and fact['subject'] != entity:
                continue
            if names is not None and fact['predicate'] not in names:
                continue
            self._retire(fact, reason)

    def _unknown_filesystem_location(self, reason):
        location = self._entity(origin='unknown_location_after_unmodeled_effect')
        self._fact('session', 'cwd', {'location_id': location, 'value': None},
                   basis='unknown filesystem location after ' + reason)

    def _forget_all(self, reason):
        # This method is also called by legacy filesystem mutation fallbacks.
        # Keep its conservative filesystem behavior without harming other APIs.
        domain = self.event.get('domain', FS_DOMAIN) if self.event else FS_DOMAIN
        scope = FS_DOMAIN if domain == FS_DOMAIN else None
        self._invalidate(scope, reason=reason)
        self._unknown_filesystem_location(reason)

    def _apply_invalidations(self, effect):
        reset_fs = False
        for item in effect['invalidations']:
            domain = item.get('domain', effect['domain'])
            entity = item.get('entity')
            fields = item.get('fields')
            reason = item.get('reason', 'unmodeled_effect')
            self._invalidate(domain, entity, fields, reason)
            if domain in (None, FS_DOMAIN) and entity is None and fields is None:
                reset_fs = True
        if reset_fs:
            self._unknown_filesystem_location('explicit conservative invalidation')

    def _apply_updates(self, effect):
        for update in effect['updates']:
            identity = self._entity(update['entity'], origin='observed_domain_entity')
            if self.nodes[identity]['domain'] != effect['domain']:
                raise ValueError('Adapter update crossed a domain boundary')
            self._edge(self.event['id'], 'acts_on', identity, role='observed_entity',
                       rule=self.event['rule'])
            for field, value in update['fields'].items():
                self._fact(identity, 'attribute.' + field, value)

    def _apply_operation(self, effect):
        operation = effect.get('operation') or {}
        if not operation:
            return
        self.event['operation_kind'] = operation['kind']
        if operation['kind'] != 'delete_latest_message':
            # The event keeps explicit unsupported operation coverage. Never
            # silently execute an unknown adapter operation as a state update.
            self.event['coverage'] = 'unmodeled'
            self._invalidate(effect['domain'], reason='unsupported_adapter_operation')
            return
        receiver = operation.get('receiver_id')
        if effect['domain'] != 'MessageAPI' or type(receiver) not in (str, int):
            raise ValueError('Invalid message deletion contract')
        target = self._entity(entity_id('MessageAPI', 'user', receiver),
                              origin='receiver_identified_by_deletion')
        self._edge(self.event['id'], 'acts_on', target, role='receiver_thread',
                   rule=self.event['rule'])
        for node in list(self.graph['nodes']):
            if node['category'] != 'object' or node.get('domain') != 'MessageAPI' or node.get('entity_type') != 'message':
                continue
            receiver_fact = self._get(node['id'], 'attribute.receiver_id')
            if receiver_fact and _same(receiver_fact['value'], receiver):
                self._using(receiver_fact, 'receiver_thread_resolution')
                self._invalidate('MessageAPI', node['id'], ['exists', 'current_thread'],
                                 'deleted_message_identity_not_returned')
        # The BFCL inbox does not store returned message IDs, and value-equal
        # duplicates can be removed by list.remove. Never assert a specific
        # message exists=False solely from the returned receiver ID.

    def _execute(self, call, raw, output_ref):
        self.step += 1
        args = call['arguments'] if isinstance(call['arguments'], dict) else {}
        effect = domain_effect(call['tool'], args, raw)
        self.refs = [call['call_evidence'], output_ref]
        self.event = {'id': f'a{self.step}', 'category': 'event', 'step': self.step,
                      **call, 'output_raw': deepcopy(raw), 'output': deepcopy(effect['parsed_output']),
                      'output_evidence': output_ref, 'status': effect['status'],
                      'error': deepcopy(effect['error']), 'status_basis': effect['basis'],
                      'outcome_basis': effect['basis'], 'domain': effect['domain'],
                      'coverage': effect['coverage'], 'footprint': effect['footprint'],
                      'operation_kind': None,
                      'rule': f"{REGISTRY_VERSION}:{effect['method']}",
                      'goal_refs': self.goals.copy()}
        self._add(self.event)
        self._apply_invalidations(effect)
        if effect['domain'] == FS_DOMAIN:
            cwd = self._get('session', 'cwd')
            if cwd is None:
                self._unknown_filesystem_location('missing current-location evidence')
                cwd = self._get('session', 'cwd')
            scope = cwd['value']['location_id']
            if cwd['first_observed_at'] < self.step:
                self._using(cwd, 'relative_path_context')
            for field in ('source','destination','file_name','file_name1','file_name2','folder','dir_name'):
                self._resolve(scope, args.get(field), field)
            if effect['status'] in ('success', 'noop') and effect['method'] in FS_READS | FS_WRITES:
                description = self._filesystem(effect['method'], args, effect['parsed_output'], scope)
            else:
                description = 'Filesystem execution outcome recorded; no unsupported successful effect inferred.'
        else:
            self._apply_updates(effect)
            self._apply_operation(effect)
            description = 'Recorded visible domain evidence; filesystem facts are unchanged.'
            if effect['domain'] == 'Unknown':
                description = 'Unknown tool footprint; explicit conservative invalidation recorded.'
        for index, observation in enumerate(effect['observations']):
            self._fact(self.event['id'], 'observation.' + observation['kind'],
                       deepcopy(observation), key=str(index))
        self.event['description'] = description

    def validate(self):
        super().validate()
        for node in self.graph['nodes']:
            if node['category'] == 'event':
                assert node['domain'] in DOMAINS | {'Unknown'}
                assert node['status'] in ('success', 'error', 'noop', 'unknown')
                assert all(key in node for key in ('coverage','footprint','outcome_basis','operation_kind'))
            elif node['category'] == 'object':
                assert all(key in node for key in ('domain','entity_type','domain_id'))
            elif node['category'] == 'fact':
                assert node['domain'] == self.nodes[node['subject']]['domain']
                assert node['fact_scope'] in ('state','observation')
        return True
