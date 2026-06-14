import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TokenBlacklist:
    def __init__(self):
        self._blacklist: dict[str, float] = {}
        self._lock = threading.Lock()
        self._cleanup_interval = 300
        self._last_cleanup = time.time()

    def add(self, jti: str, exp: float) -> None:
        with self._lock:
            self._blacklist[jti] = exp
            logger.info(f"Token blacklisted: {jti[:8]}...")
        self._maybe_cleanup()

    def is_blacklisted(self, jti: str) -> bool:
        with self._lock:
            exp = self._blacklist.get(jti)
            if exp is None:
                return False
            if time.time() > exp:
                del self._blacklist[jti]
                return False
            return True

    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        with self._lock:
            expired = [jti for jti, exp in self._blacklist.items() if now > exp]
            for jti in expired:
                del self._blacklist[jti]
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired blacklist entries")
            self._last_cleanup = now

    def size(self) -> int:
        with self._lock:
            return len(self._blacklist)


token_blacklist = TokenBlacklist()
