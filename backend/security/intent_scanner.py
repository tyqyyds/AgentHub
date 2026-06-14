import re
from typing import Dict, List, Any


class IntentScanner:
    KEYWORD_BLACKLIST = [
        "delete", "shutdown", "reset", "format", "rm -rf",
        "drop table", "truncate", "wipe", "destroy", "kill -9",
        "fork bomb", "dd if=", ":(){ :|:& };:"
    ]

    SQL_INJECTION_PATTERNS = [
        r"(?i)(\b(union\s+select|select\s+.+\s+from|insert\s+into|update\s+.+\s+set|delete\s+from)\b)",
        r"(?i)(\b(or|and)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?)",
        r"(?i)(\b(exec(\s+|\()|execute\s+)\w+)",
        r"(?i)(--\s*$|/\*|\*/|;\s*--)",
        r"(?i)(\b(waitfor\s+delay|benchmark\s*\(|sleep\s*\())",
        r"(?i)(\bchar\s*\(|concat\s*\(|0x[0-9a-f]+)",
    ]

    SHELL_INJECTION_PATTERNS = [
        r"[;&|`$]",
        r"\$\([^)]+\)",
        r"\$\{[^}]+\}",
        r"(?i)(\b(bash|sh|cmd|powershell|python|perl|ruby|php)\b\s*[-/]c\b)",
        r"(?i)(\b(nc|ncat|netcat|wget|curl)\s+)",
        r"(?i)(\b(chmod|chown|chgrp)\s+)",
        r"(?i)(\b(sudo|su)\s+)",
    ]

    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.\\",
        r"(?i)(\b/etc/passwd\b|\b/etc/shadow\b|\b/etc/hosts\b)",
        r"(?i)(\b(c:\\|d:\\)\b)",
        r"(?i)(\b\.\./\b.*\b\.\./\b)",
    ]

    def __init__(self):
        self._compiled_sql = [re.compile(p) for p in self.SQL_INJECTION_PATTERNS]
        self._compiled_shell = [re.compile(p) for p in self.SHELL_INJECTION_PATTERNS]
        self._compiled_path = [re.compile(p) for p in self.PATH_TRAVERSAL_PATTERNS]

    def scan(self, user_input: str) -> Dict[str, Any]:
        threats: List[str] = []
        risk_level = "safe"

        lower_input = user_input.lower()
        for keyword in self.KEYWORD_BLACKLIST:
            if keyword.lower() in lower_input:
                threats.append(f"keyword_blacklist: {keyword}")
                risk_level = "high"

        for pattern in self._compiled_sql:
            match = pattern.search(user_input)
            if match:
                threats.append(f"sql_injection: {match.group()}")
                if risk_level not in ("high",):
                    risk_level = "medium"

        for pattern in self._compiled_shell:
            match = pattern.search(user_input)
            if match:
                threats.append(f"shell_injection: {match.group()}")
                if risk_level not in ("high",):
                    risk_level = "medium"

        for pattern in self._compiled_path:
            match = pattern.search(user_input)
            if match:
                threats.append(f"path_traversal: {match.group()}")
                if risk_level not in ("high",):
                    risk_level = "medium"

        return {
            "is_malicious": risk_level in ("high", "medium"),
            "threats": threats,
            "risk_level": risk_level
        }

    def scan_structured_params(self, params: dict) -> Dict[str, Any]:
        all_threats: List[str] = []
        overall_risk = "safe"

        for key, value in params.items():
            if isinstance(value, str):
                result = self.scan(value)
                all_threats.extend(result["threats"])
                if result["risk_level"] == "high":
                    overall_risk = "high"
                elif result["risk_level"] == "medium" and overall_risk != "high":
                    overall_risk = "medium"
            elif isinstance(value, dict):
                result = self.scan_structured_params(value)
                all_threats.extend(result["threats"])
                if result["risk_level"] == "high":
                    overall_risk = "high"
                elif result["risk_level"] == "medium" and overall_risk != "high":
                    overall_risk = "medium"
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        result = self.scan(item)
                        all_threats.extend(result["threats"])
                        if result["risk_level"] == "high":
                            overall_risk = "high"
                        elif result["risk_level"] == "medium" and overall_risk != "high":
                            overall_risk = "medium"

        return {
            "is_malicious": overall_risk in ("high", "medium"),
            "threats": all_threats,
            "risk_level": overall_risk
        }


intent_scanner = IntentScanner()
