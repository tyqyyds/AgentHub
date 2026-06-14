import re
import uuid
import logging
from typing import List, Dict, Any, Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeQAAgent:
    def __init__(self):
        self._documents: List[Dict[str, Any]] = []
        self._rag_engine = None
        self._rag_available = False
        self._init_rag()
        self._load_default_knowledge()

    def _init_rag(self):
        try:
            from backend.knowledge.rag_engine import get_rag_engine
            self._rag_engine = get_rag_engine()
            self._rag_available = self._rag_engine.available
            if self._rag_available:
                logger.info("KnowledgeQAAgent initialized with RAG engine")
            else:
                logger.info("RAG engine not available, using keyword matching fallback")
        except Exception as e:
            logger.warning(f"Failed to initialize RAG engine: {e}, using keyword matching fallback")
            self._rag_engine = None
            self._rag_available = False

    def _load_default_knowledge(self):
        default_docs = [
            {
                "title": "QoS配置完整指南",
                "content": """QoS（服务质量）配置完整指南

一、QoS基本概念
QoS通过分类、标记、队列调度和限速等机制保障关键业务流量优先转发。

二、华为设备QoS配置步骤
1. 定义流量分类
  traffic classifier voip
   if-match dscp ef
  traffic classifier data
   if-match dscp af21

2. 定义流行为
  traffic behavior voip
   car cir 10000 pir 12000  // 承诺速率10Mbps，峰值12Mbps
   queue llq  // 低延迟队列，适合语音
  traffic behavior data
   car cir 5000 pir 8000
   queue wfq  // 加权公平队列

3. 定义流策略
  traffic policy qos-policy
   classifier voip behavior voip
   classifier data behavior data

4. 应用到接口
  interface GigabitEthernet0/0/1
   traffic-policy qos-policy outbound

三、思科设备QoS配置
1. class-map match-all VOICE
   match dscp ef
2. policy-map QOS-POLICY
   class VOICE
    priority percent 30
   class class-default
    fair-queue
3. interface Gi0/1
   service-policy output QOS-POLICY

四、验证命令
- display traffic policy statistics interface GigabitEthernet0/0/1
- show policy-map interface Gi0/1

五、常见问题
- 策略未生效：检查接口方向（inbound/outbound）
- 带宽不足：调整CIR/PIR参数
- 语音卡顿：确保语音流量进入LLQ队列""",
            },
            {
                "title": "OSPF路由协议配置与故障排查",
                "content": """OSPF路由协议配置与故障排查

一、OSPF基本原理
OSPF是链路状态路由协议，使用SPF算法计算最短路径。区域划分减少LSA泛洪范围。

二、华为设备OSPF配置
1. 基本配置
  ospf 1 router-id 10.1.1.1
   area 0
    network 10.1.1.0 0.0.0.255
   area 1
    network 192.168.1.0 0.0.0.255

2. 接口开销调整
  interface GigabitEthernet0/0/1
   ospf cost 10

3. 路由汇总（ABR上配置）
  ospf 1
   area 1
    abr-summary 192.168.0.0 255.255.252.0

三、常见故障排查
1. 邻居无法建立
   - 检查：display ospf peer
   - 原因：MTU不匹配、子网掩码不一致、area ID错误
   - 解决：接口配置ospf mtu-enable，确认network宣告正确

2. 路由丢失
   - 检查：display ospf routing
   - 原因：接口cost过大、过滤策略、区域未与area 0直连
   - 解决：调整cost值，检查filter-policy，确保虚链路配置

3. SPF频繁计算
   - 检查：display ospf spf-statistics
   - 原因：网络不稳定、接口频繁up/down
   - 解决：配置ospf timer spf-max-interval限制计算频率""",
            },
            {
                "title": "BGP故障排查手册",
                "content": """BGP故障排查手册

一、BGP邻居建立失败排查
1. 检查TCP连接
   - display tcp status  // 确认179端口是否监听
   - ping对端地址  // 确认网络连通性

2. 检查BGP配置
   - display bgp peer  // 查看邻居状态
   - 状态说明：Idle→Connect→Active→OpenSent→OpenConfirm→Established
   - 卡在Active：对端未配置peer或AS号不匹配
   - 卡在OpenSent：AS号或Router ID冲突

3. 常见原因
   - AS号配置错误
   - Router ID冲突
   - 认证密码不匹配
   - EBGP多跳未配置（非直连EBGP邻居）
   - 解决：peer x.x.x.x ebgp-max-hop 2

二、BGP路由未接收排查
1. 检查路由发布
   - display bgp routing-table  // 查看BGP路由表
   - display bgp routing-table peer x.x.x.x received-routes

2. 常见原因
   - 未配置network或import-route
   - route-policy过滤了路由
   - next-hop不可达（IBGP场景）
   - 解决：配置next-hop-local或确保IGP可达

三、路由震荡处理
1. 配置dampening抑制震荡路由
   - dampening 15 750 3000 60
2. 调整Keepalive和Hold Time
   - timer keepalive 30 hold 90""",
            },
            {
                "title": "VLAN配置与端口安全",
                "content": """VLAN配置与端口安全

一、华为设备VLAN配置
1. 批量创建VLAN
  vlan batch 10 20 30 100-200

2. 接入端口配置
  interface GigabitEthernet0/0/1
   port link-type access
   port default vlan 10

3. 中继端口配置
  interface GigabitEthernet0/0/24
   port link-type trunk
   port trunk allow-pass vlan 10 20 30

4. Hybrid端口配置
  interface GigabitEthernet0/0/2
   port link-type hybrid
   port hybrid tagged vlan 10 20
   port hybrid untagged vlan 30

二、端口安全配置
1. 限制MAC地址学习数量
  interface GigabitEthernet0/0/1
   port-security enable
   port-security max-mac-num 2
   port-security protect-action shutdown  // 违规动作：关闭端口

2. 绑定MAC地址
  interface GigabitEthernet0/0/1
   port-security mac-address sticky
   port-security max-mac-num 1

三、VLAN间路由
1. 三层交换机配置
  interface Vlanif10
   ip address 192.168.10.1 24
  interface Vlanif20
   ip address 192.168.20.1 24

2. 验证命令
   - display vlan
   - display port-security interface GigabitEthernet0/0/1""",
            },
            {
                "title": "防火墙策略配置规范",
                "content": """防火墙策略配置规范

一、安全策略基本原则
1. 默认拒绝：所有未明确允许的流量一律拒绝
2. 最小权限：仅开放业务必需的端口和协议
3. 从上到下匹配：策略按顺序匹配，命中即执行
4. 定期审计：每月检查策略有效性，清理过期规则

二、华为防火墙配置
1. 创建安全区域
  firewall zone trust
   add interface GigabitEthernet0/0/1
  firewall zone untrust
   add interface GigabitEthernet0/0/2

2. 配置安全策略
  security-policy
   rule name allow-web
    source-zone trust
    destination-zone untrust
    source-address 192.168.1.0 24
    destination-address any
    service http https
    action permit

3. NAT配置
  nat-policy
   rule name snat
    source-zone trust
    destination-zone untrust
    source-address 192.168.1.0 24
    action source-nat easy-ip

三、思科ASA防火墙
1. ACL配置
  access-list OUTSIDE_IN extended permit tcp any host 203.0.113.10 eq 80
  access-list OUTSIDE_IN extended deny ip any any
  access-group OUTSIDE_IN in interface outside

2. NAT配置
  object network OBJ-INTERNAL
   subnet 192.168.1.0 255.255.255.0
   nat (inside,outside) dynamic interface

四、安全注意事项
- 禁止配置any-to-any的permit规则
- 管理端口仅允许运维网段访问
- 定期备份策略配置
- 变更前必须确认回滚方案""",
            },
            {
                "title": "设备巡检完整要点",
                "content": """设备巡检完整要点

一、日常巡检项目（每日）
1. 设备状态检查
   - CPU使用率：display cpu-usage（正常<70%）
   - 内存使用率：display memory-usage（正常<80%）
   - 设备温度：display device temperature（正常<70°C）

2. 接口状态检查
   - display interface brief  // 查看接口up/down状态
   - 重点关注：错包率、丢包率、带宽利用率
   - 带宽利用率>80%需关注，>90%需扩容

3. 告警检查
   - display alarm active  // 当前活跃告警
   - display logbuffer  // 系统日志

二、周度巡检项目
1. 路由表检查
   - display ip routing-table statistics
   - 对比上周路由数量，异常增长需排查

2. 安全检查
   - 检查登录日志：display aaa online-record
   - 检查配置变更：display configuration commit list

3. 冗余检查
   - HA状态：display ha service-status
   - BFD会话：display bfd session all

三、月度巡检项目
1. 配置备份
   - backup configuration
   - 验证备份文件完整性

2. 版本检查
   - display version  // 检查是否需要升级
   - 查看安全公告，评估补丁需求

3. 性能基线更新
   - 记录各设备CPU/内存/带宽基线值
   - 对比历史趋势，识别异常""",
            },
            {
                "title": "网络故障自愈体系",
                "content": """网络故障自愈体系

一、自愈流程四步闭环
1. 检测（Detection）：通过监控指标发现异常
   - 指标：接口状态变化、流量突降、延迟升高、丢包率上升
   - 工具：SNMP Trap、NetStream、BFD

2. 诊断（Diagnosis）：分析故障根因
   - 方法：拓扑分析、日志关联、配置比对、流量分析
   - 输出：根因定位+影响范围+修复方案

3. 修复（Remediation）：执行自动修复
   - 低风险：路由切换、接口重启、策略调整
   - 高风险：设备重启、配置回滚（需人工审批）

4. 验证（Verification）：确认修复效果
   - 方法：ping测试、流量对比、业务验证
   - 失败则触发回滚或升级处理

二、关键指标
- MTTD（平均检测时间）：< 1分钟
- MTTR（平均修复时间）：< 5分钟
- 自愈成功率：> 95%
- 误操作率：< 0.1%

三、灰度自愈策略
1. 先在1%流量上验证修复效果
2. 逐步扩大到10%→50%→100%
3. 每步验证业务指标正常后才继续
4. 任何步骤异常立即回滚""",
            },
            {
                "title": "流量工程与MPLS配置",
                "content": """流量工程与MPLS配置

一、MPLS-TE基本概念
MPLS流量工程通过建立TE隧道实现流量优化，支持显式路径和动态路径。

二、华为设备MPLS-TE配置
1. 全局使能MPLS
  mpls lsr-id 10.1.1.1
  mpls
   mpls te
   mpls rsvp-te
   mpls te cspf

2. 接口使能MPLS-TE
  interface GigabitEthernet0/0/1
   mpls
   mpls te
   mpls rsvp-te

3. 创建TE隧道
  interface Tunnel1
   ip address unnumbered Loopback0
   tunnel-protocol mpls te
   destination 10.2.2.2
   mpls te tunnel-id 1
   mpls te path explicit-path path1
   mpls te bandwidth 10000  // 预留10G带宽

4. 显式路径配置
  explicit-path path1
   next hop 10.1.1.2
   next hop 10.2.2.2

三、流量引入TE隧道
1. 静态路由引入
  ip route-static 192.168.0.0 255.255.0.0 Tunnel1

2. 策略路由引入
  route-policy pbr-te permit node 10
   if-match acl 2000
   apply output-interface Tunnel1

四、验证命令
- display mpls te tunnel-interface
- display mpls te cspf destination
- display rsvp-te session""",
            },
            {
                "title": "常见网络故障排查手册",
                "content": """常见网络故障排查手册

一、Ping不通排查流程
1. 检查本机网络配置
   - ipconfig / ifconfig  // 确认IP/掩码/网关
   - ping 127.0.0.1  // 测试协议栈
   - ping 本机IP  // 测试网卡

2. 逐跳排查
   - ping 网关  // 测试二层连通性
   - ping 目标IP  // 测试端到端连通性
   - tracert / traceroute  // 定位断点位置

3. 常见原因
   - ARP未学习：display arp，检查MAC表
   - 路由缺失：display ip routing-table
   - ACL拦截：display acl statistics
   - 防火墙策略：检查安全策略

二、端口不通排查流程
1. 确认端口状态
   - telnet x.x.x.x port  // 测试TCP端口
   - nc -zv x.x.x.x port  // netcat测试

2. 排查步骤
   - 检查服务是否启动：netstat -tlnp
   - 检查防火墙规则：iptables -L -n
   - 检查端口安全策略
   - 检查NAT映射是否正确

三、丢包排查流程
1. 定位丢包位置
   - ping -c 1000 网关  // 测试本段
   - ping -c 1000 下一跳  // 逐段测试
   - mtr x.x.x.x  // 持续traceroute

2. 常见原因
   - 接口错包：display interface，检查CRC错误
   - 队列溢出：检查带宽利用率
   - 双工不匹配：检查接口协商状态
   - 光衰过大：检查光功率

四、延迟高排查
1. 定位延迟位置
   - traceroute分析每跳延迟
   - 对比不同时段延迟变化

2. 常见原因
   - 链路拥塞：检查带宽利用率
   - 队列调度不合理：检查QoS配置
   - 设备CPU过高：display cpu-usage
   - 路由环路：检查路由表""",
            },
            {
                "title": "Linux运维常用命令与脚本",
                "content": """Linux运维常用命令与脚本

一、系统监控
1. 资源监控
   - top / htop  // 实时进程监控
   - vmstat 1 5  // 虚拟内存统计
   - iostat -x 1  // IO统计
   - sar -n DEV 1  // 网络流量统计

2. 网络监控
   - ss -tlnp  // 查看监听端口
   - netstat -an | grep ESTABLISHED | wc -l  // 连接数
   - tcpdump -i eth0 -nn port 80  // 抓包
   - nethogs  // 按进程查看流量

二、故障排查
1. 磁盘问题
   - df -h  // 磁盘使用率
   - du -sh /*  // 目录大小
   - lsof +D /path  // 查看占用文件的进程
   - fuser -v /path  // 查看占用目录的进程

2. 内存问题
   - free -h  // 内存使用
   - ps aux --sort=-%mem | head  // 内存占用TOP
   - pmap -x PID  // 进程内存映射

3. 网络问题
   - nslookup domain  // DNS解析
   - curl -v http://url  // HTTP请求调试
   - mtr x.x.x.x  // 网络质量检测

三、常用运维脚本
1. 端口开放（firewalld）
   firewall-cmd --permanent --add-port=8080/tcp
   firewall-cmd --reload

2. 端口开放（iptables）
   iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
   service iptables save

3. 系统信息收集
   #!/bin/bash
   echo "=== CPU ===" && cat /proc/cpuinfo | grep "model name" | head -1
   echo "=== Memory ===" && free -h
   echo "=== Disk ===" && df -h
   echo "=== Network ===" && ip addr show
   echo "=== Uptime ===" && uptime""",
            },
        ]
        for doc in default_docs:
            doc_id = str(uuid.uuid4())[:8]
            doc["id"] = doc_id
            self._documents.append(doc)

            if self._rag_available and self._rag_engine:
                try:
                    self._rag_engine.add_document(
                        doc_id=doc_id,
                        title=doc["title"],
                        content=doc["content"],
                    )
                except Exception as e:
                    logger.warning(f"Failed to add document {doc_id} to RAG engine: {e}")

        logger.info(f"Loaded {len(default_docs)} default knowledge documents (RAG: {self._rag_available})")

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text.lower())
        result = []
        for token in tokens:
            if re.match(r'[\u4e00-\u9fff]+', token):
                for i in range(len(token)):
                    for j in range(i + 1, min(i + 4, len(token) + 1)):
                        result.append(token[i:j])
            else:
                result.append(token)
        return list(set(result))

    def _keyword_query(self, question: str) -> Dict[str, Any]:
        question_tokens = self._tokenize(question)
        if not question_tokens:
            return {
                "answer": "无法理解您的问题，请提供更详细的描述。",
                "sources": [],
                "confidence": 0.0,
            }

        scored_docs = []
        for doc in self._documents:
            doc_tokens = self._tokenize(doc["title"] + " " + doc["content"])
            matched = set(question_tokens) & set(doc_tokens)
            if matched:
                score = len(matched) / len(question_tokens)
                scored_docs.append((doc, score, matched))

        scored_docs.sort(key=lambda x: x[1], reverse=True)

        if not scored_docs or scored_docs[0][1] < 0.05:
            return {
                "answer": "未找到与您问题相关的知识条目，建议联系运维专家或查阅更多文档。",
                "sources": [],
                "confidence": 0.1,
            }

        best_doc, raw_confidence, matched_keywords = scored_docs[0]
        confidence = min(raw_confidence, 0.95)

        sources = [
            {"title": doc["title"], "score": round(score, 4)}
            for doc, score, _ in scored_docs[:3]
            if score >= 0.05
        ]

        return {
            "answer": best_doc["content"],
            "sources": sources,
            "confidence": round(confidence, 4),
        }

    def query(self, question: str) -> Dict[str, Any]:
        if self._rag_available and self._rag_engine:
            try:
                results = self._rag_engine.hybrid_search(
                    question,
                    top_k=settings.rag_top_k,
                    threshold=settings.rag_similarity_threshold,
                )
                if results:
                    sources = [
                        {"title": r.title, "score": round(r.score, 4)}
                        for r in results[:3]
                    ]
                    confidence = min(results[0].score, 0.95)
                    return {
                        "answer": results[0].content,
                        "sources": sources,
                        "confidence": round(confidence, 4),
                    }
            except Exception as e:
                logger.warning(f"RAG search failed, falling back to keyword matching: {e}")

        return self._keyword_query(question)

    async def query_with_rag(self, question: str) -> Dict[str, Any]:
        if self._rag_available and self._rag_engine:
            try:
                search_results = self._rag_engine.hybrid_search(
                    question, top_k=settings.rag_top_k,
                    threshold=settings.rag_similarity_threshold,
                )
                if not search_results:
                    return {
                        "answer": "未找到与您问题相关的知识条目，建议联系运维专家或查阅更多文档。",
                        "sources": [],
                        "confidence": 0.0,
                        "retrieval_method": "hybrid",
                    }

                context_parts = []
                sources = []
                for r in search_results[:5]:
                    context_parts.append(f"[{r.title}]\n{r.content}")
                    sources.append({"title": r.title, "score": round(r.score, 4)})

                context_text = "\n\n".join(context_parts)
                confidence = min(search_results[0].score, 0.95)

                try:
                    from backend.agents.llm_gateway import get_llm_gateway, TaskType
                    gateway = get_llm_gateway()
                    prompt = f"""基于以下知识库内容回答用户问题。如果知识库中没有相关信息，请明确说明。

知识库内容：
{context_text}

用户问题：{question}

请用中文简洁专业地回答："""

                    llm_result = await gateway.chat(
                        messages=[
                            {"role": "system", "content": "你是智维AgentHub的知识库问答助手，基于提供的知识库内容回答问题。"},
                            {"role": "user", "content": prompt},
                        ],
                        task_type=TaskType.QA,
                        temperature=0.3,
                        max_tokens=1024,
                    )
                    answer = llm_result.get("content", search_results[0].content)
                except Exception as llm_err:
                    logger.warning(f"LLM generation failed, using top result: {llm_err}")
                    answer = search_results[0].content

                return {
                    "answer": answer,
                    "sources": sources,
                    "confidence": round(confidence, 4),
                    "retrieval_method": "hybrid",
                }
            except Exception as e:
                logger.warning(f"RAG hybrid search failed, falling back: {e}")

        return self._keyword_query(question)

    def add_document(self, title: str, content: str) -> Dict[str, Any]:
        doc_id = str(uuid.uuid4())[:8]
        doc = {"id": doc_id, "title": title, "content": content}
        self._documents.append(doc)

        if self._rag_available and self._rag_engine:
            try:
                self._rag_engine.add_document(
                    doc_id=doc_id,
                    title=title,
                    content=content,
                )
            except Exception as e:
                logger.warning(f"Failed to add document to RAG engine: {e}")

        logger.info(f"Added knowledge document: {title}")
        return doc

    def upload_document(self, file_path: str, title: str = "") -> Dict[str, Any]:
        try:
            from backend.knowledge.document_parser import document_parser
            parsed = document_parser.parse_file(file_path)

            doc_title = title or parsed.title
            doc_id = str(uuid.uuid4())[:8]
            doc = {"id": doc_id, "title": doc_title, "content": parsed.content}
            self._documents.append(doc)

            if self._rag_available and self._rag_engine:
                try:
                    self._rag_engine.add_document(
                        doc_id=doc_id,
                        title=doc_title,
                        content=parsed.content,
                        metadata={
                            "source_file": parsed.source_file,
                            "format": parsed.metadata.get("format", "unknown"),
                            "sections": len(parsed.sections),
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to add uploaded document to RAG engine: {e}")

            logger.info(f"Uploaded document: {doc_title} from {file_path}")
            return {
                "id": doc_id,
                "title": doc_title,
                "content_length": len(parsed.content),
                "sections": len(parsed.sections),
                "metadata": parsed.metadata,
            }
        except Exception as e:
            logger.error(f"Document upload failed: {e}")
            return {"error": str(e)}

    def delete_document(self, doc_id: str) -> bool:
        for i, doc in enumerate(self._documents):
            if doc.get("id") == doc_id:
                removed = self._documents.pop(i)

                if self._rag_available and self._rag_engine:
                    try:
                        self._rag_engine.delete_document(doc_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete document from RAG engine: {e}")

                logger.info(f"Deleted knowledge document: {removed.get('title', doc_id)}")
                return True
        return False

    def list_documents(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": doc.get("id", ""),
                "name": doc.get("title", ""),
                "type": "text",
                "size": len(doc.get("content", "")),
            }
            for doc in self._documents
        ]


qa_agent = KnowledgeQAAgent()
