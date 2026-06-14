import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CommitConfirmed")

class CommitConfirmedManager:
    def __init__(self):
        self.pending_commits: Dict[str, "PendingCommit"] = {}
        self.default_timeout = timedelta(minutes=5)
        self.min_timeout = timedelta(seconds=30)

    def create_pending_commit(self, commit_id: str, device_id: str, 
                              commands: List[str], timeout: timedelta):
        """创建待确认的提交"""
        pending = PendingCommit(
            commit_id=commit_id,
            device_id=device_id,
            commands=commands,
            timeout=timeout,
            state="executing"
        )
        self.pending_commits[commit_id] = pending
        logger.info(f"创建待确认提交: {commit_id}")

    async def execute_with_confirm(self, device_id: str, commands: List[str], 
                                   confirm_timeout: timedelta = None,
                                   commit_id: str = None) -> Dict[str, Any]:
        """
        使用commit confirmed模式执行命令
        :param device_id: 设备ID
        :param commands: 命令列表
        :param confirm_timeout: 确认超时时间，默认5分钟
        :param commit_id: 可选的commit ID
        :return: 执行结果
        """
        timeout = confirm_timeout or self.default_timeout
        
        if timeout < self.min_timeout:
            raise ValueError(f"确认超时时间不能小于{self.min_timeout.total_seconds()}秒")

        if not commit_id:
            commit_id = self.generate_commit_id()
        
        if commit_id not in self.pending_commits:
            pending = PendingCommit(
                commit_id=commit_id,
                device_id=device_id,
                commands=commands,
                timeout=timeout,
                state="executing"
            )
            self.pending_commits[commit_id] = pending
        else:
            pending = self.pending_commits[commit_id]

        try:
            await self.send_commands_with_confirm(device_id, commands, commit_id)
            
            pending.state = "pending_confirm"
            
            success = await self.wait_for_confirmation(commit_id, timeout)
            
            if success:
                await self.send_confirm_commit(device_id, commit_id)
                pending.state = "confirmed"
                logger.info(f"Commit {commit_id} 已确认")
                return {"success": True, "commit_id": commit_id, "message": "命令执行成功并已确认"}
            else:
                await self.send_rollback(device_id, commit_id)
                pending.state = "rolled_back"
                logger.warning(f"Commit {commit_id} 已回滚")
                return {"success": False, "commit_id": commit_id, "message": "超时未确认，已自动回滚"}
                
        except Exception as e:
            pending.state = "failed"
            logger.error(f"Commit {commit_id} 执行失败: {e}")
            return {"success": False, "commit_id": commit_id, "message": f"执行失败: {e}"}
        finally:
            await asyncio.sleep(timeout.total_seconds() + 10)
            if commit_id in self.pending_commits:
                del self.pending_commits[commit_id]

    async def send_commands_with_confirm(self, device_id: str, commands: List[str], commit_id: str):
        """发送带有commit confirmed的命令"""
        logger.info(f"正在向设备 {device_id} 发送命令 (commit_id: {commit_id})")
        
        for cmd in commands:
            logger.debug(f"发送命令: {cmd}")
        
        await asyncio.sleep(1)

    async def wait_for_confirmation(self, commit_id: str, timeout: timedelta) -> bool:
        """等待确认信号"""
        end_time = datetime.now(timezone.utc) + timeout
        
        while datetime.now(timezone.utc) < end_time:
            pending = self.pending_commits.get(commit_id)
            if pending and pending.confirmed:
                return True
            
            await asyncio.sleep(1)
        
        return False

    async def send_confirm_commit(self, device_id: str, commit_id: str):
        """发送确认提交命令"""
        logger.info(f"向设备 {device_id} 发送确认提交 (commit_id: {commit_id})")
        await asyncio.sleep(0.5)

    async def send_rollback(self, device_id: str, commit_id: str):
        """发送回滚命令"""
        logger.warning(f"向设备 {device_id} 发送回滚命令 (commit_id: {commit_id})")
        await asyncio.sleep(0.5)

    def confirm_commit(self, commit_id: str):
        """手动确认提交"""
        pending = self.pending_commits.get(commit_id)
        if pending:
            pending.confirmed = True
            logger.info(f"收到手动确认: {commit_id}")

    def generate_commit_id(self) -> str:
        """生成唯一的commit ID"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        import random
        return f"commit-{timestamp}-{random.randint(1000, 9999)}"

    def get_pending_commits(self) -> List[Dict[str, Any]]:
        """获取所有待确认的提交"""
        now = datetime.now(timezone.utc)
        result = []
        
        for commit_id, pending in self.pending_commits.items():
            time_remaining = (pending.created_at + pending.timeout) - now
            result.append({
                "commit_id": commit_id,
                "device_id": pending.device_id,
                "state": pending.state,
                "time_remaining_seconds": max(0, time_remaining.total_seconds()),
                "command_count": len(pending.commands)
            })
        
        return result

    def cancel_commit(self, commit_id: str) -> bool:
        """取消待确认的提交（触发回滚）"""
        pending = self.pending_commits.get(commit_id)
        if pending and pending.state == "pending_confirm":
            pending.confirmed = False
            return True
        return False

class PendingCommit:
    def __init__(self, commit_id: str, device_id: str, commands: List[str], 
                 timeout: timedelta, state: str):
        self.commit_id = commit_id
        self.device_id = device_id
        self.commands = commands
        self.timeout = timeout
        self.state = state
        self.created_at = datetime.now(timezone.utc)
        self.confirmed = False

commit_manager = CommitConfirmedManager()