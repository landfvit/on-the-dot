"""Source-faithful pixel kit rendering and import tools."""
import hashlib
import json


def source_signature(kit):
    return hashlib.sha256(json.dumps(kit, sort_keys=True).encode()).hexdigest()
