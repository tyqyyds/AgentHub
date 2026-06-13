"""语义路由器 - 基于关键词匹配的跨域意图路由，轻量级实现（不依赖外部ML模型）"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RouteRule:
    """路由规则"""
    pattern: str
    handler: str
    priority: int = 0

    def matches(self, intent: str) -> bool:
        """检查意图是否匹配此规则（关键词包含匹配）"""
        return self.pattern in intent


class SemanticRouter:
    """语义路由器 - 根据意图关键词路由到目标Agent

    轻量级实现，基于关键词包含匹配，不依赖外部ML模型。
    支持多Agent匹配和优先级排序。
    """

    def __init__(self) -> None:
        self._routes: list[RouteRule] = []
        self._register_default_routes()
        logger.info("语义路由器初始化完成，已注册 %d 条默认路由", len(self._routes))

    def _register_default_routes(self) -> None:
        """注册README中定义的9种意图路由"""
        default_routes = [
            # 带宽保障 → PolicyPlanner
            ("带宽保障", "PolicyPlanner", 5),
            # 流量调度 → PolicyPlanner
            ("流量调度", "PolicyPlanner", 5),
            # 故障自愈 → ExecutionAgent, GrayscaleHealing
            ("故障自愈", "ExecutionAgent", 5),
            ("故障自愈", "GrayscaleHealing", 4),
            # 安全策略 → SecurityAgent
            ("安全策略", "SecurityAgent", 5),
            # QoS优化 → PolicyPlanner
            ("QoS优化", "PolicyPlanner", 5),
            # 链路保护 → PolicyPlanner
            ("链路保护", "PolicyPlanner", 5),
            # 负载均衡 → PolicyPlanner
            ("负载均衡", "PolicyPlanner", 5),
            # 访问控制 → SecurityAgent
            ("访问控制", "SecurityAgent", 5),
            # 路由优化 → PolicyPlanner
            ("路由优化", "PolicyPlanner", 5),
        ]
        for pattern, handler, priority in default_routes:
            self._routes.append(RouteRule(pattern=pattern, handler=handler, priority=priority))

    def register_route(self, pattern: str, handler: str, priority: int = 0) -> None:
        """注册路由规则

        Args:
            pattern: 意图关键词模式（如"故障自愈"、"带宽保障"）
            handler: 目标Agent ID
            priority: 优先级（数字越大优先级越高）
        """
        rule = RouteRule(pattern=pattern, handler=handler, priority=priority)
        self._routes.append(rule)
        logger.info("路由规则注册: pattern='%s' → handler='%s', priority=%d", pattern, handler, priority)

    async def route(self, intent: str, context: dict = None) -> list[str]:
        """根据意图路由到目标Agent

        Args:
            intent: 用户意图文本
            context: 可选的上下文信息（预留扩展用）

        Returns:
            匹配的Agent ID列表（按优先级降序排序）
        """
        matched: list[RouteRule] = []
        for rule in self._routes:
            if rule.matches(intent):
                matched.append(rule)

        # 按优先级降序排序
        matched.sort(key=lambda r: r.priority, reverse=True)

        # 提取Agent ID（去重，保持优先级顺序）
        seen: set[str] = set()
        result: list[str] = []
        for rule in matched:
            if rule.handler not in seen:
                seen.add(rule.handler)
                result.append(rule.handler)

        if result:
            logger.info("意图 '%s' 路由到: %s", intent, result)
        else:
            logger.warning("意图 '%s' 无匹配路由", intent)

        return result

    def get_routes(self) -> list[dict]:
        """获取所有路由规则

        Returns:
            路由规则列表，每项包含 pattern、handler、priority
        """
        return [
            {
                "pattern": rule.pattern,
                "handler": rule.handler,
                "priority": rule.priority,
            }
            for rule in self._routes
        ]

    def remove_route(self, pattern: str, handler: str) -> bool:
        """删除路由规则

        Args:
            pattern: 意图关键词模式
            handler: 目标Agent ID

        Returns:
            是否成功删除（True=已删除，False=未找到匹配规则）
        """
        original_len = len(self._routes)
        self._routes = [
            r for r in self._routes
            if not (r.pattern == pattern and r.handler == handler)
        ]
        removed = len(self._routes) < original_len
        if removed:
            logger.info("路由规则删除: pattern='%s' → handler='%s'", pattern, handler)
        else:
            logger.warning("未找到匹配路由规则: pattern='%s' → handler='%s'", pattern, handler)
        return removed
