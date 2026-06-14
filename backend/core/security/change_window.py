from datetime import datetime, time, timedelta
from backend.core.config import settings

class ChangeWindowManager:
    def __init__(self):
        self.start_time = self._parse_time(settings.change_window_start)
        self.end_time = self._parse_time(settings.change_window_end)
    
    def _parse_time(self, time_str: str) -> time:
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return time(8, 0)
    
    def is_within_window(self) -> bool:
        now = datetime.now().time()
        
        if self.start_time <= self.end_time:
            return self.start_time <= now <= self.end_time
        else:
            return now >= self.start_time or now <= self.end_time
    
    def get_time_until_window(self) -> int:
        now = datetime.now().time()
        
        if self.is_within_window():
            return 0
        
        if now < self.start_time:
            diff = (datetime.combine(datetime.today(), self.start_time) - 
                    datetime.combine(datetime.today(), now))
        else:
            next_day_start = datetime.combine(datetime.today(), self.start_time) + \
                            timedelta(days=1)
            diff = next_day_start - datetime.combine(datetime.today(), now)
        
        return int(diff.total_seconds() / 60)
    
    def can_proceed(self, is_emergency: bool = False) -> dict:
        if is_emergency:
            return {
                "allowed": True,
                "reason": "紧急变更允许执行",
                "is_emergency": True
            }
        
        if self.is_within_window():
            return {
                "allowed": True,
                "reason": "当前在允许变更时间段内",
                "is_emergency": False
            }
        
        minutes_until = self.get_time_until_window()
        return {
            "allowed": False,
            "reason": f"当前不在变更窗口内，距离下一个窗口还有 {minutes_until} 分钟",
            "minutes_until_window": minutes_until,
            "is_emergency": False
        }

change_window_manager = ChangeWindowManager()