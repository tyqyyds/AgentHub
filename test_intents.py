import requests
import json
import time

BASE_URL = "http://localhost:8000"

# Login
login_resp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

intents = [
    "保证财务子网到核心ERP系统的流量最小500M带宽",
    "阻断生产网中非业务时段（22:00-06:00）的P2P下载流量",
    "允许办公网通过HTTPS访问互联网，禁止其他非网页流量",
    "确保视频会议系统（IP段192.168.10.0/24）到云会议平台的最低延迟不超过50ms",
    "开放研发网到测试环境数据库的MySQL端口（3306）访问",
    "限制访客Wi-Fi子网的上行带宽最大不超过20Mbps",
    "保证核心交易系统到灾备中心的同步流量最低200M带宽，且路径优先走专线",
    "阻止外部IP段（黑名单列表）对内部Web服务的访问",
    "允许运维网通过SSH跳板机访问所有服务器，禁止直连",
    "保证直播推流子网的上行带宽最小100M，且丢包率低于0.1%",
    "在周末凌晨2:00-4:00自动临时扩容海外加速线路的带宽至1G",
    "禁止办公网内MAC地址不绑定的设备访问内网资源",
    "确保远程办公VPN用户的音频流量获得最高QoS队列优先级",
    "开放营销网到大数据平台Hadoop集群的HDFS端口（8020）双向访问",
    "当主出口链路丢包率超过2%时，自动将交互式流量（SSH/RDP）切换至备用链路",
    "保证物联网设备上报数据的流量最低50M带宽，允许突发峰值至150M",
    "限制视频监控子网回传录像的带宽峰值不超过300M，避免挤占办公流量",
    "允许外部合作伙伴的特定IP段通过IPsec隧道访问内部文件服务器",
    "保证呼叫中心SIP信令流量的延迟低于30ms，抖动小于5ms",
    "在每日9:30-10:00开盘高峰期，为证券交易子网预留对称200M带宽并禁用P2P",
]

results = {"success": [], "fail": [], "error": []}

for i, intent_text in enumerate(intents, 1):
    print(f"\n[{i}/20] 测试: {intent_text[:40]}...")
    try:
        # First parse with DeepSeek
        parse_resp = requests.post(f"{BASE_URL}/api/v2/deepseek/parse",
            headers=headers, 
            json={"user_input": intent_text},
            timeout=30
        )
        
        if parse_resp.status_code != 200:
            print(f"  解析失败: HTTP {parse_resp.status_code}")
            results["error"].append({"intent": intent_text, "stage": "parse", "status": parse_resp.status_code, "detail": parse_resp.text[:200]})
            continue
            
        parse_data = parse_resp.json()
        if parse_data.get("status") != "success" or not parse_data.get("parsed"):
            print(f"  解析返回非成功: {json.dumps(parse_data, ensure_ascii=False)[:200]}")
            results["error"].append({"intent": intent_text, "stage": "parse", "detail": json.dumps(parse_data, ensure_ascii=False)[:200]})
            continue
        
        p = parse_data["parsed"]
        valid_names = ['git_clone_bandwidth_guarantee', 'bandwidth_guarantee', 'fault_diagnosis', 'performance_monitoring', 'qos_policy', 'traffic_shaping', 'access_control', 'link_management', 'device_config']
        raw_name = p.get("intent_type", "")
        intent_name = raw_name if raw_name in valid_names else "bandwidth_guarantee"
        confidence = p.get("confidence", 0.5)
        is_valid = raw_name in valid_names and confidence >= 0.35
        
        print(f"  解析: intent_name={intent_name}, raw={raw_name}, confidence={confidence}, valid={is_valid}")
        
        # Submit intent
        structured_params = {
            "intent_name": intent_name,
            "targets": [p.get("target_subnet", "未知子网")] if p.get("target_subnet") else [],
            "actions": [{"type": a.get("type"), "params": a.get("params", {})} for a in (p.get("actions") or [])],
            "confidence": confidence,
            "clarification_needed": p.get("clarification_needed", False),
            "clarification_question": p.get("clarification_question"),
            "entities": p.get("entities", {}),
            "bandwidth": p.get("bandwidth"),
            "duration": p.get("duration"),
            "priority": p.get("priority", "medium"),
            "is_valid": is_valid,
        }
        
        submit_resp = requests.post(f"{BASE_URL}/api/v1/intents",
            headers=headers,
            json={"user_input": intent_text, "structured_params": structured_params},
            timeout=15
        )
        
        if submit_resp.status_code == 200:
            submit_data = submit_resp.json()
            if submit_data.get("status") == "success":
                print(f"  提交成功! ID={submit_data.get('data', {}).get('id', '?')}")
                results["success"].append({"intent": intent_text, "intent_name": intent_name, "id": submit_data.get("data", {}).get("id")})
            else:
                print(f"  提交返回非成功: {json.dumps(submit_data, ensure_ascii=False)[:200]}")
                results["fail"].append({"intent": intent_text, "intent_name": intent_name, "detail": json.dumps(submit_data, ensure_ascii=False)[:200]})
        else:
            detail = submit_resp.text[:300]
            print(f"  提交失败: HTTP {submit_resp.status_code} - {detail}")
            results["fail"].append({"intent": intent_text, "intent_name": intent_name, "status": submit_resp.status_code, "detail": detail})
            
    except Exception as e:
        print(f"  异常: {e}")
        results["error"].append({"intent": intent_text, "error": str(e)})
    
    time.sleep(0.5)  # Rate limit

print("\n" + "="*60)
print(f"测试结果汇总:")
print(f"  成功: {len(results['success'])}")
print(f"  失败: {len(results['fail'])}")
print(f"  异常: {len(results['error'])}")

if results["fail"]:
    print("\n失败详情:")
    for f in results["fail"]:
        print(f"  - {f['intent'][:40]}... | {f.get('detail', '')[:100]}")

if results["error"]:
    print("\n异常详情:")
    for e in results["error"]:
        print(f"  - {e['intent'][:40]}... | {e.get('error', e.get('detail', ''))[:100]}")
