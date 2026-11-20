"""Object-scoped state updates from reviewed tool effects, not matching field names."""
from copy import deepcopy

DOORS = ("driver", "passenger", "rear_left", "rear_right")
SCALARS = {"fuelLevel", "batteryVoltage", "engineState", "brakePedalStatus",
           "brakePedalForce", "remainingUnlockedDoors"}

class StateAccumulator:
    """Keep latest observed attribute values with explicit supersession witnesses."""
    def __init__(self):
        self.values = {}
        self.witnesses = {}
        self.edges = []

    def update(self, object_id, patch, evidence_id):
        for path, value in patch.items():
            key = (object_id, tuple(path))
            if key in self.witnesses:
                self.edges.append({"object": object_id, "attribute": list(path),
                                   "old": self.witnesses[key], "new": evidence_id,
                                   "relation": "superseded_state"})
            self.values[key] = deepcopy(value)
            self.witnesses[key] = evidence_id

    def observed(self, object_id):
        result = {}
        for (obj, path), value in self.values.items():
            if obj != object_id:
                continue
            dest = result
            for key in path[:-1]:
                dest = dest.setdefault(key, {})
            dest[path[-1]] = deepcopy(value)
        return result

def vehicle_patch(tool, args, value):
    """Canonical per-door writes; lockStatus describes named doors, not the whole car.
    Returns None for errors/unsupported/contradictory results. Caller must retain
    errors and abort a component if an operation can change state despite failure.
    """
    if not isinstance(args, dict) or not isinstance(value, dict) or value.get("error"):
        return None
    patch = {}
    used = set()
    for name in sorted(SCALARS):
        if name in value:
            patch[(name,)] = deepcopy(value[name]);used.add(name)
    if "engine_state" in value:
        if "engineState" in value and value["engineState"] != value["engine_state"]:
            return None
        patch[("engineState",)] = value["engine_state"];used.add("engine_state")
    if "doorStatus" in value:
        doors = value["doorStatus"]
        if not isinstance(doors, dict) or any(k not in DOORS or v not in ("locked", "unlocked") for k,v in doors.items()):
            return None
        patch.update({("doorStatus", k): v for k,v in doors.items()});used.add("doorStatus")
        # A full read determines the aggregate; a partial read does not.
        if set(doors) == set(DOORS):
            n = sum(v == "unlocked" for v in doors.values())
            if "remainingUnlockedDoors" in value and value["remainingUnlockedDoors"] != n:
                return None
            patch[("remainingUnlockedDoors",)] = n
    if tool == "lockDoors":
        doors = args.get("door");unlock = args.get("unlock")
        if type(unlock) is not bool or not isinstance(doors, list) or not doors or any(not isinstance(d,str) or d not in DOORS for d in doors) or len(set(doors)) != len(doors):
            return None
        status = "unlocked" if unlock else "locked"
        n = value.get("remainingUnlockedDoors")
        if value.get("lockStatus") != status or type(n) is not int or not 0 <= n <= len(DOORS):
            return None
        if len(doors) == len(DOORS) and n != (len(DOORS) if unlock else 0):
            return None
        patch.update({("doorStatus", d):status for d in doors});used.add("lockStatus")
    if not patch:
        return None
    return patch, {k:deepcopy(v) for k,v in value.items() if k not in used}
