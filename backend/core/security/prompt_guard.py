import re
from typing import List

class PromptInjectionGuard:
    def __init__(self):
        self.malicious_patterns = [
            r"(?i)ignore.*previous.*instructions?",
            r"(?i)forget.*previous.*prompt?",
            r"(?i)ignore.*context",
            r"(?i)reset.*prompt",
            r"(?i)override.*instructions?",
            r"(?i)disregard.*instructions?",
            r"(?i)pretend.*you.*are",
            r"(?i)act.*as.*if",
            r"(?i)system.*prompt",
            r"(?i)debug.*mode",
            r"(?i)developer.*mode",
            r"(?i)break.*rules",
            r"(?i)hack.*the.*system",
            r"(?i)tell.*me.*your.*secret",
            r"(?i)reveal.*your.*instructions?",
            r"(?i)show.*me.*your.*prompt",
            r"(?i)what.*is.*your.*purpose?",
            r"(?i)describe.*your.*architecture",
            r"(?i)detailed.*description.*of.*your.*design",
            r"(?i)code.*injection",
            r"(?i)sql.*inject",
            r"(?i)xss.*attack",
            r"(?i)cross.*site.*script",
            r"(?i)<script.*>",
            r"(?i)>.*<",
            r"(?i);.*--",
            r"(?i)union.*select",
            r"(?i)drop.*table",
            r"(?i)delete.*from",
            r"(?i)insert.*into",
            r"(?i)update.*set",
            r"(?i)exec.*sp_",
            r"(?i)xp_cmdshell",
            r"(?i)OR.*1=1",
            r"(?i)AND.*1=1",
            r"(?i)' OR '1'='1",
            r"(?i)\";.*--",
            r"(?i)'\);.*--",
            r"(?i)\.\./\.\./",
            r"(?i)etc/passwd",
            r"(?i)/etc/shadow",
            r"(?i)localhost:.*",
            r"(?i)127\.0\.0\.1",
            r"(?i)0\.0\.0\.0",
            r"(?i)file://",
            r"(?i)http://",
            r"(?i)https://",
            r"(?i)ftp://",
            r"(?i)sftp://",
            r"(?i)mailto:",
            r"(?i)telnet://",
            r"(?i)ssh://"
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