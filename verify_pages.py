import urllib.request
import json
import sys

BASE = "http://localhost:8000"

# Login first to get token
login_data = json.dumps({"username": "admin", "password": "admin123456"}).encode()
login_req = urllib.request.Request(
    f"{BASE}/api/v1/auth/login",
    data=login_data,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(login_req, timeout=10) as resp:
        login_resp = json.loads(resp.read().decode())
        TOKEN = login_resp.get("access_token", "")
        print(f"Login OK, token length: {len(TOKEN)}")
except Exception as e:
    print(f"Login FAILED: {e}")
    sys.exit(1)

def api_get(path):
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def api_post(path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

results = {}

# 1. Dashboard - events
print("=" * 60)
print("1. Dashboard (/dashboard)")
d = api_get("/api/v1/events")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["dashboard"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d.get("items", d.get("data", []))
    total = d.get("total", len(items))
    print(f"  Events total: {total}, items returned: {len(items)}")
    for i in items[:5]:
        eid = i.get("event_id", i.get("id", "?"))
        title = i.get("title", i.get("name", "?"))[:50]
        sev = i.get("severity", i.get("status", "?"))
        print(f"    - {eid}: {title} [{sev}]")
    results["dashboard"] = {"status": "OK", "total": total, "items": len(items)}

# 2. Intent Center
print("=" * 60)
print("2. Intent Center (/intent)")
d = api_get("/api/v1/intents")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["intent"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d.get("items", d.get("data", []))
    total = d.get("total", len(items))
    print(f"  Intents total: {total}, items returned: {len(items)}")
    for i in items[:8]:
        iid = i.get("intent_id", i.get("id", "?"))
        name = i.get("name", i.get("title", "?"))[:50]
        st = i.get("status", "?")
        print(f"    - {iid}: {name} [{st}]")
    results["intent"] = {"status": "OK", "total": total, "items": len(items)}

# 3. Topology
print("=" * 60)
print("3. Topology (/topology)")
d = api_get("/api/v1/topology")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["topology"] = {"status": "ERROR", "detail": d["error"]}
else:
    nodes = d.get("nodes", [])
    links = d.get("links", d.get("edges", []))
    print(f"  Nodes: {len(nodes)}, Links: {len(links)}")
    for n in nodes[:5]:
        nid = n.get("id", n.get("name", "?"))
        ntype = n.get("type", n.get("device_type", "?"))
        print(f"    - {nid}: {ntype}")
    results["topology"] = {"status": "OK", "nodes": len(nodes), "links": len(links)}

# 4. Self-Healing
print("=" * 60)
print("4. Self-Healing (/self-healing)")
d = api_get("/api/v1/events")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["self-healing"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d.get("items", d.get("data", []))
    total = d.get("total", len(items))
    print(f"  Events total: {total}, items returned: {len(items)}")
    results["self-healing"] = {"status": "OK", "total": total, "items": len(items)}

# 5. MCP Tools
print("=" * 60)
print("5. MCP Tools (/mcp-tools)")
d = api_get("/api/v1/mcp-tools")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["mcp-tools"] = {"status": "ERROR", "detail": d["error"]}
else:
    tools = d if isinstance(d, list) else d.get("tools", d.get("items", d.get("data", [])))
    print(f"  Tools count: {len(tools)}")
    for t in (tools if isinstance(tools, list) else [])[:7]:
        tname = t.get("name", t.get("tool_name", "?"))
        desc = t.get("description", "")[:50]
        print(f"    - {tname}: {desc}")
    results["mcp-tools"] = {"status": "OK", "count": len(tools)}

# 6. Agent Map
print("=" * 60)
print("6. Agent Map (/agent-map)")
d = api_get("/api/v1/agents")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["agent-map"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("agents", [])))
    total = len(items) if isinstance(items, list) else d.get("total", 0)
    print(f"  Agents count: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for a in (items if isinstance(items, list) else [])[:5]:
        aid = a.get("agent_id", a.get("id", "?"))
        aname = a.get("name", a.get("agent_name", "?"))[:40]
        atype = a.get("type", a.get("agent_type", "?"))
        print(f"    - {aid}: {aname} [{atype}]")
    results["agent-map"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 7. Audit Logs
print("=" * 60)
print("7. Audit Logs (/audit-logs)")
d = api_get("/api/v1/audit-logs")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["audit-logs"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d.get("items", d.get("data", d.get("logs", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Audit logs total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        lid = i.get("log_id", i.get("id", "?"))
        action = i.get("action", i.get("event_type", "?"))[:40]
        print(f"    - {lid}: {action}")
    results["audit-logs"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 8. Workflow Board
print("=" * 60)
print("8. Workflow Board (/workflow)")
d = api_get("/api/v1/workflow/board")
if "error" in d:
    # try orders endpoint
    d = api_get("/api/v1/workflow/orders")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["workflow"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("orders", d.get("cards", []))))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Workflow orders total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        oid = i.get("order_id", i.get("id", i.get("card_id", "?")))
        title = i.get("title", i.get("name", "?"))[:40]
        st = i.get("status", "?")
        print(f"    - {oid}: {title} [{st}]")
    results["workflow"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 9. Playbooks
print("=" * 60)
print("9. Playbooks (/playbooks)")
d = api_get("/api/v1/playbooks")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["playbooks"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("playbooks", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Playbooks total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        pid = i.get("playbook_id", i.get("id", "?"))
        pname = i.get("name", i.get("title", "?"))[:40]
        print(f"    - {pid}: {pname}")
    results["playbooks"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 10. Webhooks
print("=" * 60)
print("10. Webhooks (/webhooks)")
d = api_get("/api/v1/webhooks/subscriptions")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["webhooks"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("subscriptions", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Webhook subscriptions total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        sid = i.get("subscription_id", i.get("id", "?"))
        url = i.get("url", i.get("target_url", "?"))[:40]
        print(f"    - {sid}: {url}")
    results["webhooks"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 11. Users
print("=" * 60)
print("11. Users (/users)")
d = api_get("/api/v1/auth/me")
if "error" in d:
    print(f"  ERROR: {d['error']}")
else:
    print(f"  Current user: {d.get('username', '?')} (role: {d.get('role', '?')})")

# Check if there's a users endpoint
d2 = api_get("/api/v1/users")
if "error" in d2:
    print(f"  No /api/v1/users endpoint, checking auth endpoints only")
    results["users"] = {"status": "PARTIAL", "detail": "No dedicated users list API"}
else:
    items = d2 if isinstance(d2, list) else d2.get("items", d2.get("data", d2.get("users", [])))
    total = d2.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Users total: {total}")
    results["users"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 12. Knowledge
print("=" * 60)
print("12. Knowledge (/knowledge)")
d = api_get("/api/v1/knowledge/documents")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["knowledge"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("documents", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Knowledge docs total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        did = i.get("document_id", i.get("id", "?"))
        dname = i.get("title", i.get("name", "?"))[:40]
        print(f"    - {did}: {dname}")
    results["knowledge"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 13. LLM Router
print("=" * 60)
print("13. LLM Router (/llm-router)")
d = api_get("/api/v1/llm-router/providers")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["llm-router"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("providers", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  LLM providers total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        pname = i.get("name", i.get("provider_name", "?"))
        ptype = i.get("type", i.get("provider_type", "?"))
        print(f"    - {pname}: {ptype}")
    results["llm-router"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 14. Scheduler
print("=" * 60)
print("14. Scheduler (/scheduler)")
d = api_get("/api/v1/scheduler/queue")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["scheduler"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("queue", d.get("intents", []))))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Scheduler queue total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        iid = i.get("intent_id", i.get("id", "?"))
        iname = i.get("name", i.get("title", "?"))[:40]
        print(f"    - {iid}: {iname}")
    results["scheduler"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 15. SLA
print("=" * 60)
print("15. SLA (/sla)")
d = api_get("/api/v1/sla/predictions")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["sla"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("predictions", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  SLA predictions total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        iid = i.get("intent_id", i.get("id", "?"))
        pred = i.get("prediction", i.get("predicted_sla", "?"))
        print(f"    - {iid}: {pred}")
    results["sla"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 16. Observability
print("=" * 60)
print("16. Observability (/observability)")
d = api_get("/api/v1/observability/traces")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["observability"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("traces", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Traces total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        tid = i.get("trace_id", i.get("id", "?"))
        tname = i.get("name", i.get("operation", "?"))[:40]
        print(f"    - {tid}: {tname}")
    results["observability"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 17. Failed Intents
print("=" * 60)
print("17. Failed Intents (/failed-intents)")
d = api_get("/api/v1/failed-intents")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["failed-intents"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("cases", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Failed intents total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        cid = i.get("case_id", i.get("id", "?"))
        cname = i.get("name", i.get("title", "?"))[:40]
        print(f"    - {cid}: {cname}")
    results["failed-intents"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# 18. Notifications
print("=" * 60)
print("18. Notifications (/notifications)")
d = api_get("/api/v1/knowledge/notifications")
if "error" in d:
    print(f"  ERROR: {d['error']}")
    results["notifications"] = {"status": "ERROR", "detail": d["error"]}
else:
    items = d if isinstance(d, list) else d.get("items", d.get("data", d.get("notifications", [])))
    total = d.get("total", len(items) if isinstance(items, list) else 0)
    print(f"  Notifications total: {total}, items returned: {len(items) if isinstance(items, list) else 'N/A'}")
    for i in (items if isinstance(items, list) else [])[:5]:
        nid = i.get("notification_id", i.get("id", "?"))
        ntitle = i.get("title", i.get("message", "?"))[:40]
        print(f"    - {nid}: {ntitle}")
    results["notifications"] = {"status": "OK", "total": total, "items": len(items) if isinstance(items, list) else 0}

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
for page, info in results.items():
    status = info.get("status", "?")
    if status == "OK":
        total = info.get("total", info.get("count", info.get("nodes", 0)))
        items = info.get("items", 0)
        print(f"  {page}: {status} (total={total}, items={items})")
    else:
        print(f"  {page}: {status} - {info.get('detail', '')}")

# Save results as JSON
with open("d:/Trae CN/Project/智维 AgentHub/verify_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nResults saved to verify_results.json")
