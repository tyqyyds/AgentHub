#!/usr/bin/env python3
import json, urllib.request
req = urllib.request.urlopen("http://127.0.0.1:8000/openapi.json")
data = json.loads(req.read())
paths = sorted(data.get("paths", {}).keys())
for p in paths:
    methods = list(data["paths"][p].keys())
    print(f"{p}  [{', '.join(m.upper() for m in methods)}]")
