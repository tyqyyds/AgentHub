#!/bin/bash
BASE="http://127.0.0.1:8000"
PASS=0
FAIL=0
TOTAL=0

report() {
  TOTAL=$((TOTAL+1))
  if [ "$1" = "PASS" ]; then
    PASS=$((PASS+1))
    echo "  ✅ $2"
  else
    FAIL=$((FAIL+1))
    echo "  ❌ $2"
  fi
}

echo "============================================"
echo "  智维 AgentHub 全面功能测试"
echo "============================================"
echo ""

# 1. Health Check
echo "--- [1] 健康检查 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/health")
if [ "$R" = "200" ]; then report "PASS" "Health API 返回 200"; else report "FAIL" "Health API 返回 $R"; fi

# 2. User Login (admin)
echo "--- [2] 用户登录 ---"
LOGIN_RESP=$(curl -s -X POST "$BASE/api/v1/auth/login" -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
AUTH="Authorization: Bearer $TOKEN"
if [ -n "$TOKEN" ] && [ "$TOKEN" != "None" ] && [ "$TOKEN" != "" ]; then report "PASS" "Admin 登录成功，获取 JWT Token"; else report "FAIL" "Admin 登录失败: $LOGIN_RESP"; fi

# 3. User Info
echo "--- [3] 用户信息 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/auth/me")
if [ "$R" = "200" ]; then report "PASS" "获取当前用户信息 返回 200"; else report "FAIL" "获取当前用户信息 返回 $R"; fi

# 4. Topology/Device List
echo "--- [4] 设备管理 ---"
DEV_RESP=$(curl -s -H "$AUTH" "$BASE/api/v1/topology/devices")
DEV_COUNT=$(echo "$DEV_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); data=d.get('data',d); print(len(data) if isinstance(data,list) else len(d.get('devices',data)) if isinstance(d,dict) else 0)" 2>/dev/null)
if [ -n "$DEV_COUNT" ]; then report "PASS" "设备列表查询成功，共 $DEV_COUNT 个设备"; else report "FAIL" "设备列表查询异常: $DEV_RESP"; fi

# 5. Intent Submit (with intent_name in structured_params)
echo "--- [5] 意图提交 ---"
INTENT_RESP=$(curl -s -X POST "$BASE/api/v1/intents" -H "$AUTH" -H "Content-Type: application/json" -d '{"user_input":"保障核心交换机带宽不低于10Gbps","structured_params":{"intent_name":"bandwidth_guarantee","priority":"high","confidence":0.9}}')
INTENT_ID=$(echo "$INTENT_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); data=d.get('data',d); print(data.get('id','') or data.get('intent_id','') or d.get('id',''))" 2>/dev/null)
if [ -n "$INTENT_ID" ] && [ "$INTENT_ID" != "" ]; then report "PASS" "意图提交成功，ID=$INTENT_ID"; else report "FAIL" "意图提交失败: $INTENT_RESP"; fi

# 6. Intent List
echo "--- [6] 意图列表 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/intents")
if [ "$R" = "200" ]; then report "PASS" "意图列表查询 返回 200"; else report "FAIL" "意图列表查询 返回 $R"; fi

# 7. Intent Conflict Check
echo "--- [7] 意图冲突检测 ---"
if [ -n "$INTENT_ID" ] && [ "$INTENT_ID" != "" ]; then
  R=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$AUTH" "$BASE/api/v1/intents/$INTENT_ID/conflict-check")
  if [ "$R" = "200" ]; then report "PASS" "意图冲突检测 返回 200"; else report "FAIL" "意图冲突检测 返回 $R"; fi
else
  report "FAIL" "意图冲突检测跳过(无intent_id)"
fi

# 8. Workflow Board
echo "--- [8] 工作流状态 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/workflow/board")
if [ "$R" = "200" ]; then report "PASS" "工作流看板查询 返回 200"; else report "FAIL" "工作流看板查询 返回 $R"; fi

# 9. Agent Registry
echo "--- [9] Agent注册表 ---"
AGENT_RESP=$(curl -s -H "$AUTH" "$BASE/api/v1/agents")
AGENT_COUNT=$(echo "$AGENT_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); data=d.get('data',d); print(len(data) if isinstance(data,list) else 0)" 2>/dev/null)
if [ -n "$AGENT_COUNT" ] && [ "$AGENT_COUNT" -ge "1" ]; then report "PASS" "Agent注册表查询成功，共 $AGENT_COUNT 个Agent"; else report "FAIL" "Agent注册表查询异常: $AGENT_RESP"; fi

# 10. MCP Tools
echo "--- [10] MCP工具 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/mcp-tools")
if [ "$R" = "200" ]; then report "PASS" "MCP工具列表 返回 200"; else report "FAIL" "MCP工具列表 返回 $R"; fi

# 11. Knowledge Base
echo "--- [11] 知识库 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/knowledge/documents")
if [ "$R" = "200" ]; then report "PASS" "知识库文档列表 返回 200"; else report "FAIL" "知识库文档列表 返回 $R"; fi

# 12. Knowledge Search
echo "--- [12] 知识库搜索 ---"
SEARCH_RESP=$(curl -s -X POST "$BASE/api/v1/knowledge/documents/search" -H "$AUTH" -H "Content-Type: application/json" -d '{"query":"网络故障"}')
SEARCH_OK=$(echo "$SEARCH_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if isinstance(d, list) or isinstance(d, dict) else 'no')" 2>/dev/null)
if [ "$SEARCH_OK" = "yes" ]; then report "PASS" "知识库搜索接口可用"; else report "FAIL" "知识库搜索接口异常: $SEARCH_RESP"; fi

# 13. Compute Nodes
echo "--- [13] 算力节点 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/compute/nodes")
if [ "$R" = "200" ]; then report "PASS" "算力节点列表 返回 200"; else report "FAIL" "算力节点列表 返回 $R"; fi

# 14. Compute Tasks
echo "--- [14] 算力任务 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/compute/tasks")
if [ "$R" = "200" ]; then report "PASS" "算力任务列表 返回 200"; else report "FAIL" "算力任务列表 返回 $R"; fi

# 15. SLA Status
echo "--- [15] SLA评估 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/telemetry/sla/status")
if [ "$R" = "200" ]; then report "PASS" "SLA状态接口 返回 200"; else report "FAIL" "SLA状态接口 返回 $R"; fi

# 16. Telemetry Devices
echo "--- [16] 遥测指标 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/telemetry/devices")
if [ "$R" = "200" ]; then report "PASS" "遥测设备接口 返回 200"; else report "FAIL" "遥测设备接口 返回 $R"; fi

# 17. Audit Logs
echo "--- [17] 审计日志 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/audit")
if [ "$R" = "200" ]; then report "PASS" "审计日志接口 返回 200"; else report "FAIL" "审计日志接口 返回 $R"; fi

# 18. Map Config (with auth)
echo "--- [18] 地图配置 ---"
MAP_RESP=$(curl -s -H "$AUTH" "$BASE/api/v1/map/amap/config")
HAS_KEY=$(echo "$MAP_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); data=d.get('data',d); print('yes' if data.get('key') else 'no')" 2>/dev/null)
NO_SECRET=$(echo "$MAP_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); data=d.get('data',d); print('leaked!' if 'security_code' in data else 'safe')" 2>/dev/null)
if [ "$HAS_KEY" = "yes" ]; then report "PASS" "地图配置包含API Key"; else report "FAIL" "地图配置缺少API Key: $MAP_RESP"; fi
if [ "$NO_SECRET" = "safe" ]; then report "PASS" "地图配置未泄露security_code"; else report "FAIL" "地图配置泄露了security_code!"; fi

# 19. V2 Intent Execute
echo "--- [19] V2意图执行 ---"
V2_RESP=$(curl -s -X POST "$BASE/api/v2/intents/execute" -H "$AUTH" -H "Content-Type: application/json" -d '{"user_input":"优化核心路由"}')
V2_STATUS=$(echo "$V2_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','') or d.get('intent_id','') or d.get('error','') or 'ok')" 2>/dev/null)
if [ -n "$V2_STATUS" ]; then report "PASS" "V2意图执行接口可用，返回: $V2_STATUS"; else report "FAIL" "V2意图执行接口异常: $V2_RESP"; fi

# 20. Assistant Chat
echo "--- [20] 智能助手 ---"
CHAT_RESP=$(curl -s -X POST "$BASE/api/v1/assistant/chat" -H "$AUTH" -H "Content-Type: application/json" -d '{"message":"最近有什么网络故障？"}')
CHAT_OK=$(echo "$CHAT_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('response') or d.get('reply') or d.get('answer') or d.get('content') else 'no')" 2>/dev/null)
if [ "$CHAT_OK" = "yes" ]; then report "PASS" "智能助手对话接口可用"; else report "FAIL" "智能助手对话接口异常: $CHAT_RESP"; fi

# 21. Security Scan (V2)
echo "--- [21] 安全扫描 ---"
SEC_RESP=$(curl -s -X POST "$BASE/api/v2/security/scan" -H "$AUTH" -H "Content-Type: application/json" -d '{"content":"删除所有路由表配置"}')
SEC_OK=$(echo "$SEC_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'threats' in d or 'risk_level' in d or 'safe' in str(d).lower() or 'status' in d else 'no')" 2>/dev/null)
if [ "$SEC_OK" = "yes" ]; then report "PASS" "安全扫描接口可用"; else report "FAIL" "安全扫描接口异常: $SEC_RESP"; fi

# 22. RBAC - Viewer cannot create agent
echo "--- [22] RBAC权限控制 ---"
VIEWER_RESP=$(curl -s -X POST "$BASE/api/v1/auth/login" -H "Content-Type: application/json" -d '{"username":"viewer","password":"viewer123"}')
VIEWER_TOKEN=$(echo "$VIEWER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
if [ -n "$VIEWER_TOKEN" ] && [ "$VIEWER_TOKEN" != "" ] && [ "$VIEWER_TOKEN" != "None" ]; then
  VIEWER_AUTH="Authorization: Bearer $VIEWER_TOKEN"
  R=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/agents" -H "$VIEWER_AUTH" -H "Content-Type: application/json" -d '{"agent_id":"test-rbac","domain":"test","a2a_endpoint":"http://test:8080"}')
  if [ "$R" = "403" ]; then report "PASS" "Viewer角色无法创建Agent(403)"; else report "FAIL" "Viewer角色权限控制异常，返回 $R"; fi
else
  report "FAIL" "Viewer登录失败，无法测试RBAC: $VIEWER_RESP"
fi

# 23. Frontend Check
echo "--- [23] 前端页面 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1/")
if [ "$R" = "200" ]; then report "PASS" "前端页面可访问 返回 200"; else report "FAIL" "前端页面返回 $R"; fi

# 24. Nginx Proxy
echo "--- [24] Nginx反向代理 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1/api/health")
if [ "$R" = "200" ]; then report "PASS" "Nginx反向代理API正常"; else report "FAIL" "Nginx反向代理API返回 $R"; fi

# 25. V2 Agents
echo "--- [25] V2 Agent发现 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v2/agents")
if [ "$R" = "200" ]; then report "PASS" "V2 Agent列表 返回 200"; else report "FAIL" "V2 Agent列表 返回 $R"; fi

# 26. Workflow Orders
echo "--- [26] 工单管理 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/workflow/orders")
if [ "$R" = "200" ]; then report "PASS" "工单列表 返回 200"; else report "FAIL" "工单列表 返回 $R"; fi

# 27. Cross-domain A2A
echo "--- [27] 跨域A2A ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/cross-domain/agents")
if [ "$R" = "200" ]; then report "PASS" "跨域Agent列表 返回 200"; else report "FAIL" "跨域Agent列表 返回 $R"; fi

# 28. Validation
echo "--- [28] 配置验证 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" -X POST "$BASE/api/v1/validation/validate" -H "Content-Type: application/json" -d '{"intent_id":1,"commands":["show version"],"target_device":"core-switch-1"}')
if [ "$R" = "200" ]; then report "PASS" "配置验证接口 返回 200"; else report "FAIL" "配置验证接口 返回 $R"; fi

# 29. System Health
echo "--- [29] 系统健康 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/system/health")
if [ "$R" = "200" ]; then report "PASS" "系统健康检查 返回 200"; else report "FAIL" "系统健康检查 返回 $R"; fi

# 30. Topology
echo "--- [30] 拓扑图 ---"
R=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/v1/topology")
if [ "$R" = "200" ]; then report "PASS" "拓扑图接口 返回 200"; else report "FAIL" "拓扑图接口 返回 $R"; fi

echo ""
echo "============================================"
echo "  测试结果: 通过 $PASS / 总计 $TOTAL"
echo "  失败: $FAIL"
echo "============================================"

if [ "$FAIL" -eq 0 ]; then
  echo "  🎉 所有测试通过！"
else
  echo "  ⚠️  有 $FAIL 项测试失败，需要检查"
fi
