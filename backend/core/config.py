import logging
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field

logger = logging.getLogger(__name__)

DEFAULT_NETWORK_ENV = {
    "devices": [
        {"name": "core-switch-01", "ip": "10.0.0.1", "type": "huawei", "role": "core", "status": "online"},
        {"name": "core-switch-02", "ip": "10.0.0.2", "type": "huawei", "role": "core", "status": "online"},
        {"name": "agg-switch-01", "ip": "10.0.1.1", "type": "huawei", "role": "aggregation", "status": "online"},
        {"name": "agg-switch-02", "ip": "10.0.1.2", "type": "cisco", "role": "aggregation", "status": "online"},
        {"name": "access-01", "ip": "10.0.2.1", "type": "h3c", "role": "access", "status": "online"},
        {"name": "access-02", "ip": "10.0.2.2", "type": "h3c", "role": "access", "status": "warning"},
        {"name": "firewall-01", "ip": "10.0.0.254", "type": "huawei", "role": "firewall", "status": "online"}
    ],
    "subnets": [
        {"name": "研发子网", "cidr": "10.1.0.0/16", "gateway": "10.1.0.1", "devices": 45},
        {"name": "生产子网", "cidr": "10.2.0.0/16", "gateway": "10.2.0.1", "devices": 120},
        {"name": "办公子网", "cidr": "10.3.0.0/16", "gateway": "10.3.0.1", "devices": 200},
        {"name": "测试子网", "cidr": "10.4.0.0/16", "gateway": "10.4.0.1", "devices": 30}
    ],
    "active_policies": [
        {"type": "qos", "subnet": "生产子网", "min_bw": "300M", "priority": "high"},
        {"type": "acl", "source": "办公子网", "dest": "生产子网", "action": "deny"}
    ]
}

WEAK_SECRET_PATTERNS = [
    "change-me", "your_secret", "secret_key", "password", "123456",
    "admin", "default", "changeme", "test",
]


class Settings(BaseSettings):
    app_name: str = "NetOps_Intent_System"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "netops_db"
    postgres_user: str = "netops_user"
    postgres_password: str = ""

    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = ""
    influxdb_org: str = "netops"
    influxdb_bucket: str = "telemetry"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"
    llm_max_tokens: int = 4096
    llm_timeout: int = 30

    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com/v1/chat/completions"
    deepseek_model: str = "deepseek-chat"

    zhipu_api_key: str = ""
    zhipu_api_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    zhipu_model: str = "glm-4-flash"

    llm_provider_priority: str = "zhipu,deepseek"

    llm_router_enabled: bool = True
    openai_compatible_api_url: str = ""
    openai_compatible_api_key: str = ""
    openai_compatible_model: str = ""

    secret_key: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:3000,http://localhost:8090,http://127.0.0.1:8090"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 500

    device_connect_timeout: int = 10
    device_read_timeout: int = 30

    change_window_start: str = "08:00"
    change_window_end: str = "22:00"

    amap_key: str = ""
    amap_security_code: str = ""

    otel_enabled: bool = False
    otel_exporter_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agenthub"
    health_check_interval: int = 60

    rag_enabled: bool = True
    rag_embedding_model: str = "shibing624/text2vec-base-chinese"
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.3

    scheduler_enabled: bool = True
    scheduler_max_device_slots: int = 10
    scheduler_max_bandwidth_mbps: int = 10000
    scheduler_max_concurrent: int = 5
    scheduler_priority_aging_interval: int = 60
    scheduler_priority_aging_threshold: int = 300
    scheduler_rate_limit_per_type: int = 10

    sla_prediction_enabled: bool = True
    sla_prediction_horizon: int = 12
    sla_alert_threshold: float = 0.7
    sla_default_interval_high: int = 15
    sla_default_interval_medium: int = 30
    sla_default_interval_low: int = 60

    grayscale_canary_observation_seconds: int = 30
    grayscale_batch_size: int = 5
    grayscale_batch_observation_seconds: int = 15
    grayscale_auto_rollback: bool = True

    webhook_enabled: bool = True
    webhook_timeout_seconds: int = 10
    webhook_max_retries: int = 3
    prometheus_enabled: bool = True

    network_env: dict = Field(default_factory=lambda: DEFAULT_NETWORK_ENV)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v:
            logger.warning("SECRET_KEY 未设置，将在开发模式下自动生成临时密钥。生产环境请务必配置！")
            return secrets.token_urlsafe(32)
        lower = v.lower()
        for pattern in WEAK_SECRET_PATTERNS:
            if pattern in lower:
                raise ValueError(
                    f"SECRET_KEY 包含弱模式 '{pattern}'，请使用强随机密钥。"
                    f"可运行: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
        if len(v) < 32:
            raise ValueError("SECRET_KEY 长度必须至少 32 个字符")
        return v

    @field_validator("postgres_password")
    @classmethod
    def validate_postgres_password(cls, v: str) -> str:
        if not v:
            logger.warning("POSTGRES_PASSWORD 未设置，数据库连接可能失败")
            return v
        lower = v.lower()
        for pattern in ["password", "123456", "admin", "postgres"]:
            if lower == pattern:
                raise ValueError(
                    f"POSTGRES_PASSWORD 不能使用弱密码 '{v}'，请设置强密码"
                )
        return v

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    def validate_production_security(self) -> list[str]:
        issues = []
        if self.is_production:
            if not self.zhipu_api_key and not self.deepseek_api_key:
                issues.append("生产环境必须配置至少一个 LLM API 密钥 (ZHIPU_API_KEY 或 DEEPSEEK_API_KEY)")
            if not self.postgres_password:
                issues.append("生产环境必须设置 POSTGRES_PASSWORD")
            if len(self.secret_key) < 32:
                issues.append("生产环境 SECRET_KEY 长度必须 >= 32 字符")
            if self.debug:
                issues.append("生产环境不应开启 DEBUG 模式")
        return issues

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

if settings.is_production:
    security_issues = settings.validate_production_security()
    if security_issues:
        for issue in security_issues:
            logger.critical(f"安全配置错误: {issue}")
        raise RuntimeError(f"生产环境安全检查未通过: {'; '.join(security_issues)}")
