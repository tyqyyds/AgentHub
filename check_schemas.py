#!/usr/bin/env python3
import json, urllib.request
req = urllib.request.urlopen("http://127.0.0.1:8000/openapi.json")
data = json.loads(req.read())
schemas = data.get("components", {}).get("schemas", {})
for name in sorted(schemas.keys()):
    if "intent" in name.lower() or "Intent" in name:
        print(f"\n=== {name} ===")
        print(json.dumps(schemas[name], indent=2, ensure_ascii=False))
