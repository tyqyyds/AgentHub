from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import logging
import random
from collections import deque
import os
import json
from backend.core.security.rbac import get_current_user, requires_permission
from backend.core.config import settings

router = APIRouter()

logger = logging.getLogger(__name__)

# 数据持久化文件
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "rate_limit_data.json")

class RateLimitHistory:
    def __init__(self):
        self.history = deque(maxlen=50)
        self.total_requests = 0
        self.allowed_requests = 0
        self.limited_requests = 0
        self.current_rate = 0
        self.limit_threshold = 1000
        # 初始化时加载数据
        self._load_data()
        # 如果没有历史数据，生成一些初始数据
        if len(self.history) == 0:
            self._generate_initial_data()
        logger.info(f"RateLimitHistory 初始化完成，当前历史记录数: {len(self.history)}")
    
    def _generate_initial_data(self):
        """生成初始历史数据"""
        if settings.environment == "production":
            logger.info("生产环境跳过假数据生成")
            return
        logger.info("生成初始历史数据")
        now = datetime.now(timezone.utc)
        for i in range(20):
            time_offset = (19 - i) * 5  # 每5秒一条记录
            timestamp = now - timedelta(seconds=time_offset)
            requests = random.randint(50, 200)
            limited = random.randint(0, 20) if random.random() > 0.85 else 0
            allowed = requests - limited
            
            self.history.append({
                "timestamp": timestamp.isoformat(),
                "requests": requests,
                "allowed": allowed,
                "limited": limited
            })
            self.total_requests += requests
            self.allowed_requests += allowed
            self.limited_requests += limited
        # 设置当前速率为最后一个记录的请求数
        if self.history:
            self.current_rate = self.history[-1]["requests"]
    
    def _load_data(self):
        """从文件加载数据"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.total_requests = data.get("total_requests", 0)
                    self.allowed_requests = data.get("allowed_requests", 0)
                    self.limited_requests = data.get("limited_requests", 0)
                    self.current_rate = data.get("current_rate", 0)
                    self.limit_threshold = data.get("limit_threshold", 1000)
                    # 加载历史记录
                    history_list = data.get("history", [])
                    for item in history_list:
                        self.history.append(item)
                    logger.info(f"从 {DATA_FILE} 加载了 {len(self.history)} 条历史记录")
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
    
    def _save_data(self):
        """保存数据到文件"""
        try:
            data = {
                "total_requests": self.total_requests,
                "allowed_requests": self.allowed_requests,
                "limited_requests": self.limited_requests,
                "current_rate": self.current_rate,
                "limit_threshold": self.limit_threshold,
                "history": list(self.history)
            }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"数据已保存到 {DATA_FILE}")
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
    
    def add_record(self, requests: int, allowed: int, limited: int):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requests": requests,
            "allowed": allowed,
            "limited": limited
        }
        self.history.append(record)
        self.total_requests += requests
        self.allowed_requests += allowed
        self.limited_requests += limited
        self.current_rate = requests
        # 保存数据
        self._save_data()
        logger.debug(f"添加记录: requests={requests}, allowed={allowed}, limited={limited}")
    
    def get_history(self, limit: int = 20) -> list:
        history = list(self.history)[-limit:]
        logger.debug(f"获取 {len(history)} 条历史记录")
        return history
    
    def reset(self):
        self.history = deque(maxlen=50)
        self.total_requests = 0
        self.allowed_requests = 0
        self.limited_requests = 0
        self.current_rate = 0
        # 保存数据
        self._save_data()
        logger.info("限流统计已重置")

rate_limit_history = RateLimitHistory()

class RateLimitRecord(BaseModel):
    timestamp: str
    requests: int
    allowed: int
    limited: int

class RateLimitStats(BaseModel):
    total_requests: int
    allowed_requests: int
    limited_requests: int
    current_rate: int
    limit_threshold: int
    status: str

class RateLimitHistoryResponse(BaseModel):
    status: str
    data: List[RateLimitRecord]

class RateLimitStatusResponse(BaseModel):
    status: str
    data: RateLimitStats
    history: List[RateLimitRecord]

@router.get("/status", response_model=RateLimitStatusResponse)
async def get_rate_limit_status(current_user=Depends(get_current_user)):
    history = rate_limit_history.get_history(20)
    
    rate = rate_limit_history.current_rate
    threshold = rate_limit_history.limit_threshold
    percentage = (rate / threshold) * 100 if threshold > 0 else 0
    
    if percentage >= 90:
        status = "error"
    elif percentage >= 70:
        status = "warning"
    else:
        status = "normal"
    
    return RateLimitStatusResponse(
        status="success",
        data=RateLimitStats(
            total_requests=rate_limit_history.total_requests,
            allowed_requests=rate_limit_history.allowed_requests,
            limited_requests=rate_limit_history.limited_requests,
            current_rate=rate_limit_history.current_rate,
            limit_threshold=rate_limit_history.limit_threshold,
            status=status
        ),
        history=history
    )

@router.get("/history", response_model=RateLimitHistoryResponse)
async def get_rate_limit_history(limit: int = 20, current_user=Depends(get_current_user)):
    history = rate_limit_history.get_history(limit)
    return RateLimitHistoryResponse(
        status="success",
        data=history
    )

@router.post("/record")
async def record_rate_limit(request: RateLimitRecord, current_user=Depends(requires_permission("system:manage"))):
    rate_limit_history.add_record(request.requests, request.allowed, request.limited)
    return {"status": "success", "message": "记录添加成功"}

@router.post("/reset")
async def reset_rate_limit(current_user=Depends(requires_permission("system:manage"))):
    rate_limit_history.reset()
    return {"status": "success", "message": "限流统计已重置"}

@router.get("/simulate")
async def simulate_traffic(current_user=Depends(get_current_user)):
    if settings.environment != "development":
        raise HTTPException(status_code=404, detail="Not available in production")
    new_requests = random.randint(50, 200)
    limit_rate = random.randint(0, 20) if random.random() > 0.1 else 0
    allowed = new_requests - limit_rate
    
    rate_limit_history.add_record(new_requests, allowed, limit_rate)
    
    return {
        "status": "success",
        "requests": new_requests,
        "allowed": allowed,
        "limited": limit_rate
    }