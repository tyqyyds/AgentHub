import redis
import time
from backend.core.config import settings

class RateLimiter:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db
        )
        self.max_requests_per_minute = settings.max_requests_per_minute
        self.max_requests_per_hour = settings.max_requests_per_hour
    
    def is_allowed(self, client_id: str) -> bool:
        current_time = int(time.time())
        minute_key = f"rate_limit:minute:{client_id}"
        hour_key = f"rate_limit:hour:{client_id}"
        
        minute_count = self.redis_client.incr(minute_key)
        hour_count = self.redis_client.incr(hour_key)
        
        if minute_count == 1:
            self.redis_client.expire(minute_key, 60)
        if hour_count == 1:
            self.redis_client.expire(hour_key, 3600)
        
        if minute_count > self.max_requests_per_minute:
            return False
        
        if hour_count > self.max_requests_per_hour:
            return False
        
        return True
    
    def get_remaining(self, client_id: str) -> dict:
        current_time = int(time.time())
        minute_key = f"rate_limit:minute:{client_id}"
        hour_key = f"rate_limit:hour:{client_id}"
        
        minute_remaining = max(0, self.max_requests_per_minute - int(self.redis_client.get(minute_key) or 0))
        hour_remaining = max(0, self.max_requests_per_hour - int(self.redis_client.get(hour_key) or 0))
        
        return {
            "minute_remaining": minute_remaining,
            "hour_remaining": hour_remaining,
            "minute_limit": self.max_requests_per_minute,
            "hour_limit": self.max_requests_per_hour
        }

rate_limiter = RateLimiter()