import re
import ast
import html
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ThreatLevel(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityScanResult:
    is_safe: bool
    threat_level: ThreatLevel
    threats: List[Dict[str, Any]]
    sanitized_commands: List[str]
    scan_time: str

class SecuritySandbox:
    DANGEROUS_COMMANDS = [
        (r"delete\s+system", "CRITICAL", "删除系统文件"),
        (r"erase\s+flash:", "CRITICAL", "擦除闪存"),
        (r"format\s+disk", "CRITICAL", "格式化磁盘"),
        (r"shutdown\s+now", "HIGH", "立即关机"),
        (r"\breboot\b", "HIGH", "非计划重启"),
        (r"\bhalt\b", "HIGH", "停机指令"),
        (r"\bpoweroff\b", "HIGH", "关机指令"),
        (r"no\s+shutdown", "SAFE", "启用接口"),
        (r"write\s+erase", "CRITICAL", "清除配置"),
        (r"write\s+memory", "LOW", "保存配置"),
        (r"clear\s+logging", "MEDIUM", "清除日志"),
        (r"clear\s+arp", "LOW", "清除ARP表"),
        (r"clear\s+mac\s+address", "MEDIUM", "清除MAC表"),
        (r"clear\s+counters", "LOW", "清除计数器"),
        (r"no\s+ip\s+route", "MEDIUM", "删除路由"),
        (r"no\s+access-list", "MEDIUM", "删除ACL"),
        (r"no\s+interface", "HIGH", "删除接口配置"),
        (r"factory.reset", "CRITICAL", "恢复出厂设置"),
        (r"reset\s+saved", "CRITICAL", "清除保存配置"),
        (r"reset\s+system", "CRITICAL", "重置系统"),
    ]

    MALICIOUS_PATTERNS = [
        (r"(curl|wget)\s+.*\|\s*(bash|sh)", "CRITICAL", "远程脚本执行"),
        (r"(powershell|cmd)\s+/c\s+", "HIGH", "系统命令执行"),
        (r"(chmod|chown)\s+777", "HIGH", "危险权限修改"),
        (r"(rm\s+-rf|del\s+/[sfq])", "CRITICAL", "递归强制删除"),
        (r"(nc|ncat|netcat)\s+-[elp]", "HIGH", "反向Shell"),
        (r"(crypto|miner|xmrig|stratum)", "CRITICAL", "挖矿脚本特征"),
        (r"(eval|exec)\s*\(", "HIGH", "动态代码执行"),
        (r"(import\s+os|subprocess|os\.system)", "MEDIUM", "系统调用导入"),
        (r";\s*(rm|del|format|shutdown|reboot)", "CRITICAL", "命令链注入"),
        (r"&&\s*(rm|del|format|shutdown|reboot)", "CRITICAL", "命令链注入"),
        (r"\|\s*(bash|sh|python|perl|ruby|nc)", "HIGH", "管道命令执行"),
        (r"\$\{.*\}", "MEDIUM", "变量替换注入"),
        (r"\$\([^)]+\)", "HIGH", "命令替换注入"),
        (r"`[^`]+`", "HIGH", "反引号命令替换"),
        (r"(\.\./){2,}", "HIGH", "路径遍历攻击"),
        (r"/etc/(passwd|shadow|hosts)", "CRITICAL", "敏感文件访问"),
        (r"(SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*\s+FROM", "HIGH", "SQL注入特征"),
        (r"UNION\s+(ALL\s+)?SELECT", "HIGH", "SQL联合注入"),
        (r"OR\s+1\s*=\s*1", "HIGH", "SQL逻辑绕过"),
        (r"<script[^>]*>", "HIGH", "XSS脚本注入"),
        (r"javascript\s*:", "MEDIUM", "JavaScript协议注入"),
        (r"on(error|load|click|mouseover)\s*=", "MEDIUM", "事件处理器注入"),
        (r"(base64|hex|rot13)\s+-[d]", "MEDIUM", "编码解码执行"),
        (r"(ssh|telnet|ftp)\s+.*-p\s+\d+", "MEDIUM", "远程连接尝试"),
        (r"(dd\s+if=|mkfs\.|fdisk)", "CRITICAL", "磁盘操作指令"),
        (r"(iptables|firewall-cmd|ufw)\s+-[ADFI]", "HIGH", "防火墙规则篡改"),
        (r"(crontab|at\s+|systemctl\s+enable)", "MEDIUM", "定时任务/服务持久化"),
    ]

    CHINESE_DANGEROUS_KEYWORDS = [
        ("删除系统", "CRITICAL", "删除系统意图"),
        ("删除所有", "CRITICAL", "批量删除意图"),
        ("删除配置", "HIGH", "删除配置意图"),
        ("清除配置", "HIGH", "清除配置意图"),
        ("清除所有", "CRITICAL", "批量清除意图"),
        ("恢复出厂", "CRITICAL", "恢复出厂设置意图"),
        ("格式化", "HIGH", "格式化磁盘意图"),
        ("擦除", "HIGH", "擦除数据意图"),
        ("关机", "MEDIUM", "关机意图"),
        ("重启设备", "MEDIUM", "重启设备意图"),
        ("注入攻击", "CRITICAL", "注入攻击意图"),
        ("提权", "HIGH", "权限提升意图"),
        ("后门", "CRITICAL", "后门植入意图"),
        ("绕过验证", "HIGH", "绕过安全验证意图"),
        ("绕过防火墙", "HIGH", "绕过防火墙意图"),
        ("漏洞利用", "CRITICAL", "漏洞利用意图"),
        ("越权访问", "HIGH", "越权访问意图"),
        ("暴力破解", "HIGH", "暴力破解意图"),
        ("端口扫描", "MEDIUM", "端口扫描意图"),
        ("嗅探", "MEDIUM", "网络嗅探意图"),
        ("中间人攻击", "CRITICAL", "中间人攻击意图"),
        ("拒绝服务", "HIGH", "拒绝服务攻击意图"),
        ("数据窃取", "CRITICAL", "数据窃取意图"),
        ("权限提升", "HIGH", "权限提升意图"),
        ("远程控制", "HIGH", "远程控制意图"),
        ("命令注入", "CRITICAL", "命令注入意图"),
        ("SQL注入", "CRITICAL", "SQL注入意图"),
        ("跨站脚本", "HIGH", "XSS攻击意图"),
        ("攻击", "MEDIUM", "攻击意图"),
        ("漏洞", "MEDIUM", "漏洞利用意图"),
        ("绕过", "MEDIUM", "安全绕过意图"),
        ("注入", "MEDIUM", "注入意图"),
        ("后门程序", "CRITICAL", "后门程序意图"),
        ("木马", "CRITICAL", "木马程序意图"),
        ("病毒", "HIGH", "病毒相关意图"),
        ("恶意代码", "CRITICAL", "恶意代码意图"),
        ("爆破", "HIGH", "暴力破解意图"),
        ("弱口令", "MEDIUM", "弱口令探测意图"),
        ("未授权", "HIGH", "未授权访问意图"),
    ]

    OBFUSCATION_PATTERNS = [
        (r"\\x[0-9a-fA-F]{2}", "MEDIUM", "十六进制编码绕过"),
        (r"\\u[0-9a-fA-F]{4}", "MEDIUM", "Unicode编码绕过"),
        (r"\\[0-7]{3}", "MEDIUM", "八进制编码绕过"),
        (r"%[0-9a-fA-F]{2}", "LOW", "URL编码特征"),
        (r"&#[0-9]+;", "LOW", "HTML实体编码"),
        (r"&#x[0-9a-fA-F]+;", "LOW", "HTML十六进制编码"),
        (r"\b\w+\s*\+\s*\w+\s*\+\s*\w+", "MEDIUM", "字符串拼接绕过"),
        (r"\$\(echo\s+['\"]", "HIGH", "动态命令构造"),
        (r"eval\s*\(\s*['\"]", "HIGH", "动态代码执行"),
        (r"base64\s+-d\s*\|", "HIGH", "Base64解码管道执行"),
    ]

    COMMAND_CHAIN_SEPARATORS = re.compile(
        r'[;|&`$\(\)]'
    )

    def _normalize_input(self, text: str) -> str:
        normalized = text
        try:
            normalized = html.unescape(normalized)
        except Exception as e:
            logger.warning(f"HTML unescape failed: {e}")
        try:
            decoded = urllib.parse.unquote(normalized)
            if decoded != normalized:
                normalized = decoded
        except Exception as e:
            logger.warning(f"URL unquote failed: {e}")
        hex_entity_pattern = re.compile(r'\\x([0-9a-fA-F]{2})')
        normalized = hex_entity_pattern.sub(lambda m: chr(int(m.group(1), 16)), normalized)
        unicode_pattern = re.compile(r'\\u([0-9a-fA-F]{4})')
        normalized = unicode_pattern.sub(lambda m: chr(int(m.group(1), 16)), normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _detect_obfuscation(self, text: str) -> List[Dict[str, Any]]:
        threats = []
        for pattern, level, desc in self.OBFUSCATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                threats.append({
                    "input": text[:100],
                    "pattern": pattern,
                    "level": level,
                    "description": desc,
                    "type": "obfuscation"
                })
        return threats

    def _detect_command_chaining(self, cmd: str) -> List[Dict[str, Any]]:
        threats = []
        separators = self.COMMAND_CHAIN_SEPARATORS.findall(cmd)
        if len(separators) >= 2:
            threats.append({
                "command": cmd[:100],
                "level": "HIGH",
                "description": f"多重命令链接 ({len(separators)}个分隔符)",
                "type": "command_chaining"
            })
        return threats

    def _scan_chinese_keywords(self, text: str) -> List[Dict[str, Any]]:
        threats = []
        for keyword, level, desc in self.CHINESE_DANGEROUS_KEYWORDS:
            if keyword in text:
                threats.append({
                    "input": text[:100],
                    "keyword": keyword,
                    "level": level,
                    "description": desc,
                    "type": "chinese_dangerous_keyword"
                })
        return threats

    def scan_commands(self, commands: List[str]) -> SecurityScanResult:
        threats = []
        sanitized = []

        for cmd in commands:
            normalized = self._normalize_input(cmd)
            cmd_threats = self._scan_single_command(normalized)
            cmd_threats.extend(self._detect_command_chaining(normalized))
            cmd_threats.extend(self._detect_obfuscation(cmd))

            if cmd_threats:
                threats.extend(cmd_threats)
                if any(t["level"] in ["CRITICAL", "HIGH"] for t in cmd_threats):
                    sanitized.append(f"# BLOCKED: {cmd}")
                else:
                    sanitized.append(cmd)
            else:
                sanitized.append(cmd)

        threat_level = ThreatLevel.SAFE
        if threats:
            levels = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "SAFE": 0}
            max_level = max(levels.get(t["level"], 0) for t in threats)
            level_map = {4: ThreatLevel.CRITICAL, 3: ThreatLevel.HIGH, 2: ThreatLevel.MEDIUM, 1: ThreatLevel.LOW}
            threat_level = level_map.get(max_level, ThreatLevel.SAFE)

        return SecurityScanResult(
            is_safe=threat_level in [ThreatLevel.SAFE, ThreatLevel.LOW],
            threat_level=threat_level,
            threats=threats,
            sanitized_commands=sanitized,
            scan_time=datetime.now().isoformat()
        )

    def _scan_single_command(self, cmd: str) -> List[Dict[str, Any]]:
        threats = []

        for pattern, level, desc in self.DANGEROUS_COMMANDS:
            if re.search(pattern, cmd, re.IGNORECASE):
                if level != "SAFE":
                    threats.append({
                        "command": cmd,
                        "pattern": pattern,
                        "level": level,
                        "description": desc,
                        "type": "dangerous_command"
                    })

        for pattern, level, desc in self.MALICIOUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                threats.append({
                    "command": cmd,
                    "pattern": pattern,
                    "level": level,
                    "description": desc,
                    "type": "malicious_pattern"
                })

        return threats

    def scan_natural_language(self, text: str) -> SecurityScanResult:
        normalized = self._normalize_input(text)
        threats = []

        for pattern, level, desc in self.MALICIOUS_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                threats.append({
                    "input": normalized[:100],
                    "pattern": pattern,
                    "level": level,
                    "description": desc,
                    "type": "malicious_input"
                })

        threats.extend(self._scan_chinese_keywords(normalized))
        threats.extend(self._detect_obfuscation(text))

        threat_level = ThreatLevel.SAFE
        if threats:
            levels = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
            max_level = max(levels.get(t["level"], 0) for t in threats)
            level_map = {4: ThreatLevel.CRITICAL, 3: ThreatLevel.HIGH, 2: ThreatLevel.MEDIUM, 1: ThreatLevel.LOW}
            threat_level = level_map.get(max_level, ThreatLevel.SAFE)

        sanitized_text = text
        for threat in threats:
            pattern = threat.get("pattern", "")
            if pattern and len(pattern) >= 3:
                sanitized_text = sanitized_text.replace(pattern, "[REDACTED]")

        return SecurityScanResult(
            is_safe=threat_level in [ThreatLevel.SAFE, ThreatLevel.LOW],
            threat_level=threat_level,
            threats=threats,
            sanitized_commands=[sanitized_text] if sanitized_text != text else [text],
            scan_time=datetime.now().isoformat()
        )



