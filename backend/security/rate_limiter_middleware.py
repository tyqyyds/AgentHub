import time
from typing import Dict, Tuple, Optional
from collections import defaultdict
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse


class SlidingWindowCounter:
    def __init__(self, window_seconds: int = 60):
        self._window_seconds = window_seconds
        self._counters: Dict[str, Dict[float, int]] = defaultdict(dict)

    def _cleanup(self, key: str):
        now = time.time()
        cutoff = now - self._window_seconds
        timestamps_to_remove = [
            ts for ts in self._counters[key] if ts < cutoff
        ]
        for ts in timestamps_to_remove:
            del self._counters[key][ts]

    def increment(self, key: str) -> Tuple[int, float]:
        now = time.time()
        self._cleanup(key)
        bucket = now - (now % 1)
        self._counters[key][bucket] = self._counters[key].get(bucket, 0) + 1
        total = sum(self._counters[key].values())
        oldest = min(self._counters[key].keys()) if self._counters[key] else now
        reset_at = oldest + self._window_seconds
        return total, reset_at

    def get_count(self, key: str) -> int:
        self._cleanup(key)
        return sum(self._counters[key].values())

    def reset(self, key: str):
        if key in self._counters:
            del self._counters[key]


ROLE_RATE_LIMITS = {
    "admin": {"write": 500, "read": 2000},
    "operator": {"write": 100, "read": 500},
    "viewer": {"write": 20, "read": 200},
    "unauthenticated": {"write": 0, "read": 30},
}

DEV_ROLE_RATE_LIMITS = {
    "admin": {"write": None, "read": None},
    "operator": {"write": None, "read": None},
    "viewer": {"write": None, "read": None},
    "unauthenticated": {"write": 50, "read": 500},
}

AUTH_RATE_LIMITS = {
    "/api/v1/auth/login": {"max_attempts": 10, "window_seconds": 300},
    "/api/v1/auth/register": {"max_attempts": 5, "window_seconds": 3600},
}

WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
READ_METHODS = {"GET", "OPTIONS"}

BYPASS_PATHS = (
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi",
    "/api/v1/knowledge/chat/stream",
    "/api/v1/auth/init-admin",
)


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, window_seconds: int = 60):
        self.app = app
        self._write_counter = SlidingWindowCounter(window_seconds)
        self._read_counter = SlidingWindowCounter(window_seconds)
        self._auth_counter = SlidingWindowCounter(300)
        self._rate_limits: Optional[dict] = None

    def _get_rate_limits(self) -> dict:
        if self._rate_limits is not None:
            return self._rate_limits
        try:
            from backend.core.config import settings
            if getattr(settings, 'environment', 'production') != 'production':
                self._rate_limits = DEV_ROLE_RATE_LIMITS
            else:
                self._rate_limits = ROLE_RATE_LIMITS
        except Exception:
            self._rate_limits = DEV_ROLE_RATE_LIMITS
        return self._rate_limits

    def _get_role(self, scope: dict) -> str:
        headers = dict(
            (k.decode() if isinstance(k, bytes) else k, v.decode() if isinstance(v, bytes) else v)
            for k, v in scope.get("headers", [])
        )
        auth_header = headers.get("authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return "unauthenticated"

        token = auth_header[7:]
        try:
            from backend.core.security.rbac import decode_token
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                return payload.get("role", "viewer")
        except Exception:
            pass
        return "unauthenticated"

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(bp) for bp in BYPASS_PATHS):
            await self.app(scope, receive, send)
            return

        auth_limit = AUTH_RATE_LIMITS.get(path)
        if auth_limit:
            client = scope.get("client")
            client_host = client[0] if client else "unknown"
            auth_key = f"auth:{client_host}:{path}"
            self._auth_counter._window_seconds = auth_limit["window_seconds"]
            current_count, reset_at = self._auth_counter.increment(auth_key)
            if current_count > auth_limit["max_attempts"]:
                retry_after = int(reset_at - time.time()) + 1
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Auth rate limit exceeded", "retry_after": retry_after},
                    headers={
                        "X-RateLimit-Limit": str(auth_limit["max_attempts"]),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(reset_at)),
                        "Retry-After": str(retry_after),
                    }
                )
                await response(scope, receive, send)
                return
            remaining = max(0, auth_limit["max_attempts"] - current_count)
            original_send = send

            async def send_with_auth_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"X-RateLimit-Limit", str(auth_limit["max_attempts"]).encode()))
                    headers.append((b"X-RateLimit-Remaining", str(remaining).encode()))
                    headers.append((b"X-RateLimit-Reset", str(int(reset_at)).encode()))
                    message["headers"] = headers
                await original_send(message)

            await self.app(scope, receive, send_with_auth_headers)
            return

        rate_limits = self._get_rate_limits()
        role = self._get_role(scope)
        limits = rate_limits.get(role, rate_limits.get("unauthenticated", {"write": 0, "read": 30}))
        method = scope.get("method", "GET").upper()

        if method in WRITE_METHODS:
            limit = limits["write"]
            counter = self._write_counter
            counter_type = "write"
        elif method in READ_METHODS:
            limit = limits["read"]
            counter = self._read_counter
            counter_type = "read"
        else:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        client_key = f"{role}:{client_host}:{counter_type}"

        if limit is None:
            original_send = send

            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"X-RateLimit-Limit", b"unlimited"))
                    headers.append((b"X-RateLimit-Remaining", b"unlimited"))
                    headers.append((b"X-RateLimit-Reset", str(int(time.time()) + 60).encode()))
                    message["headers"] = headers
                await original_send(message)

            await self.app(scope, receive, send_with_headers)
            return

        current_count, reset_at = counter.increment(client_key)
        remaining = max(0, limit - current_count)

        if current_count > limit:
            retry_after = int(reset_at - time.time()) + 1
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after": retry_after},
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_at)),
                    "Retry-After": str(retry_after),
                }
            )
            await response(scope, receive, send)
            return

        original_send = send

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"X-RateLimit-Limit", str(limit).encode()))
                headers.append((b"X-RateLimit-Remaining", str(remaining).encode()))
                headers.append((b"X-RateLimit-Reset", str(int(reset_at)).encode()))
                message["headers"] = headers
            await original_send(message)

        await self.app(scope, receive, send_with_headers)
