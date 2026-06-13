import re
from typing import List

class PromptInjectionGuard:
    """Prompt注入防护 - 58种恶意模式检测"""

    def __init__(self):
        self.malicious_patterns = [
            # ── 指令覆盖类 (9) ──
            r"(?i)ignore\s+(previous|above|all|prior)\s+(instructions|prompts|rules)",
            r"(?i)forget\s+(everything|all|previous|prior)",
            r"(?i)you\s+are\s+now\s+",
            r"(?i)pretend\s+(you\s+are|to\s+be)",
            r"(?i)act\s+as\s+(if\s+you\s+are|a|an)",
            r"(?i)disregard\s+(all|any|previous|safety)",
            r"(?i)override\s+(safety|security|previous)",
            r"(?i)bypass\s+(security|safety|restrictions|filters)",
            r"(?i)system\s*:\s*",
            # ── 系统提示泄露/越狱类 (5) ──
            r"(?i)<\|im_start\|>",
            r"(?i)\[INST\]",
            r"(?i)###\s*Instruction",
            r"(?i)jailbreak",
            r"(?i)DAN\s+mode",
            # ── 危险Shell/开发模式类 (3) ──
            r"(?i)developer\s+mode",
            r"(?i)sudo\s+rm",
            r"(?i)rm\s+-rf\s+/",
            # ── 命令注入类 (8) ──
            r"(?i);\s*rm\s+",
            r"(?i)\|\s*rm\s+",
            r"(?i)\$\(",
            r"(?i)`[^`]*`",
            r"(?i)\\x[0-9a-fA-F]{2}",
            r"(?i)\\u[0-9a-fA-F]{4}",
            r"(?i)0x[0-9a-fA-F]+",
            r"(?i)eval\s*\(",
            # ── 代码注入/执行类 (12) ──
            r"(?i)exec\s*\(",
            r"(?i)subprocess",
            r"(?i)os\.system",
            r"(?i)import\s+os",
            r"(?i)__import__",
            r"(?i)__class__",
            r"(?i)__subclasses__",
            r"(?i)__globals__",
            r"(?i)__builtins__",
            r"(?i)base64\.b64decode",
            r"(?i)pickle\.loads",
            r"(?i)yaml\.load\s*\(",
            # ── 反序列化/危险库类 (5) ──
            r"(?i)marshal\.loads",
            r"(?i)shelve\.open",
            r"(?i)webbrowser\.open",
            r"(?i)socket\.socket",
            r"(?i)requests\.(post|put|delete|patch)",
            # ── 网络通信类 (6) ──
            r"(?i)urllib\.request",
            r"(?i)http\.client",
            r"(?i)paramiko",
            r"(?i)fabric",
            r"(?i)ansible",
            r"(?i)terraform\s+(apply|destroy)",
            # ── 运维工具/系统安全类 (10) ──
            r"(?i)kubectl\s+(delete|exec)",
            r"(?i)docker\s+(rm|exec|rmi)",
            r"(?i)crontab",
            r"(?i)nohup",
            r"(?i)chmod\s+777",
            r"(?i)chown\s+root",
            r"(?i)iptables\s+-F",
            r"(?i)setenforce\s+0",
            r"(?i)systemctl\s+(stop|disable)\s+(firewall|ssh)",
        ]
        
        self.trusted_domains = [
            "netops.local",
            "internal.api",
            "localhost"
        ]
    
    def detect_injection(self, input_text: str) -> List[str]:
        matches = []
        
        for pattern in self.malicious_patterns:
            if re.search(pattern, input_text):
                matches.append(pattern)
        
        for domain in self.trusted_domains:
            if domain.lower() in input_text.lower():
                matches = [m for m in matches if "http://" not in m and "https://" not in m]
        
        return matches
    
    def is_safe(self, input_text: str) -> bool:
        return len(self.detect_injection(input_text)) == 0
    
    def sanitize(self, input_text: str) -> str:
        sanitized = input_text
        
        patterns_to_remove = [
            r"(?i)<script[^>]*>.*?</script>",
            r"(?i)<[^>]*>",
            r"(?i)javascript:",
            r"(?i)vbscript:",
            r"(?i)data:",
            r"(?i)on\w+=",
            r"(?i)'[^']*--",
            r"(?i);.*--",
            r"(?i)\/\*.*\*\/"
        ]
        
        for pattern in patterns_to_remove:
            sanitized = re.sub(pattern, "", sanitized)
        
        return sanitized.strip()

prompt_guard = PromptInjectionGuard()