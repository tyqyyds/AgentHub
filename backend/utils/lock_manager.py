import uuid
from datetime import timedelta
from typing import Optional, Dict, Any
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LockManager")

class LockManager:
    def __init__(self):
        self.lock_prefix = "netops:lock:"
        self.lock_timeout = timedelta(seconds=300)
        self.poll_interval = 5
        self._memory_locks: Dict[str, Dict[str, Any]] = {}

    async def acquire_lock(self, device_id: str, owner: str = "system") -> Optional[str]:
        if device_id in self._memory_locks:
            return None
        
        token = str(uuid.uuid4())
        self._memory_locks[device_id] = {
            "owner": owner,
            "token": token,
            "expire_at": asyncio.get_event_loop().time() + self.lock_timeout.total_seconds()
        }
        logger.info(f"设备 {device_id} 获取锁成功")
        return token

    async def acquire_lock_with_wait(self, device_id: str, owner: str = "system", timeout: int = 60) -> Optional[str]:
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            token = await self.acquire_lock(device_id, owner)
            if token:
                return token
            await asyncio.sleep(self.poll_interval)
        
        return None

    async def release_lock(self, device_id: str, token: str) -> bool:
        self._clean_expired_locks()
        
        lock_info = self._memory_locks.get(device_id)
        if lock_info and lock_info["token"] == token:
            del self._memory_locks[device_id]
            logger.info(f"设备 {device_id} 释放锁成功")
            return True
        return False

    async def is_locked(self, device_id: str) -> bool:
        self._clean_expired_locks()
        return device_id in self._memory_locks

    async def get_lock_info(self, device_id: str) -> Optional[Dict[str, str]]:
        self._clean_expired_locks()
        
        if device_id not in self._memory_locks:
            return None
        
        lock_info = self._memory_locks[device_id]
        ttl = max(0, lock_info["expire_at"] - asyncio.get_event_loop().time())
        
        return {
            "owner": lock_info["owner"],
            "token": lock_info["token"],
            "ttl": int(ttl)
        }

    async def extend_lock(self, device_id: str, token: str) -> bool:
        lock_info = self._memory_locks.get(device_id)
        if lock_info and lock_info["token"] == token:
            lock_info["expire_at"] = asyncio.get_event_loop().time() + self.lock_timeout.total_seconds()
            return True
        return False

    async def get_all_locks(self) -> Dict[str, Dict[str, Any]]:
        self._clean_expired_locks()
        
        now = asyncio.get_event_loop().time()
        locks = {}
        
        for device_id, info in self._memory_locks.items():
            locks[device_id] = {
                "owner": info["owner"],
                "token": info["token"],
                "ttl": int(info["expire_at"] - now)
            }
        
        return locks

    def _clean_expired_locks(self):
        now = asyncio.get_event_loop().time()
        expired = [device_id for device_id, info in self._memory_locks.items() 
                   if info["expire_at"] < now]
        for device_id in expired:
            del self._memory_locks[device_id]

lock_manager = LockManager()