"""Canonical display names and stable IDs for existing experimental records."""
LABELS = {
    'identity': 'Identity',
    'v1-compact': 'State-Transition Graph',
    'v2-compact': 'Event Graph',
    'v2-dedup': 'Event Graph-Dedup',
}
SHORT_LABELS = LABELS.copy()
MODES = ('identity', 'v1-compact', 'v2-compact')
ALIASES = {label: key for key,label in LABELS.items()}
ALIASES.update({'state-transition-graph':'v1-compact','event-graph':'v2-compact','event-graph-dedup':'v2-dedup'})

def method_id(value):
    """Accept a public name or stable historical ID without changing artifacts."""
    return ALIASES.get(value,value)
