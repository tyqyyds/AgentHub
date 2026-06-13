from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NetOps_Intent_System"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # ── PostgreSQL ──
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "netops_db"
    postgres_user: str = "netops_user"
    postgres_password: str = "netops_password"

    # ── InfluxDB ──
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = ""
    influxdb_org: str = "netops"
    influxdb_bucket: str = "telemetry"

    # ── Redis ──
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ── OpenAI (通用) ──
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"
    llm_max_tokens: int = 4096
    llm_timeout: int = 30

    # ── DeepSeek LLM ──
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_max_tokens: int = 4096
    deepseek_temperature: float = 0.7

    # ── 智谱 GLM ──
    zhipu_api_key: str = ""
    zhipu_model: str = "glm-4"
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_max_tokens: int = 4096
    zhipu_temperature: float = 0.7

    # ── ChromaDB ──
    chromadb_host: str = "localhost"
    chromadb_port: int = 8000
    chromadb_collection: str = "knowledge_base"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # ── JWT / 安全 ──
    secret_key: str = "dev-secret-key-change-in-production-2024"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30

    # ── 限流 ──
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 500

    # ── WebSocket ──
    ws_max_connections: int = 1000
    ws_max_connections_per_user: int = 5
    ws_heartbeat_interval: int = 30
    ws_heartbeat_timeout: int = 10
    ws_reconnect_max_retries: int = 5

    # ── 设备连接 ──
    device_connect_timeout: int = 10
    device_read_timeout: int = 30

    # ── 变更窗口 ──
    change_window_start: str = "08:00"
    change_window_end: str = "22:00"

    # ── A2A 通信 ──
    a2a_gateway_host: str = "0.0.0.0"
    a2a_gateway_port: int = 8090
    a2a_message_bus_type: str = "redis"

    # ── 可观测性 ──
    jaeger_host: str = "localhost"
    jaeger_port: int = 14268
    otel_service_name: str = "netops-orchestrator"
    prometheus_port: int = 9090

    # ── 安全策略计数 ──
    prompt_injection_patterns_count: int = 58
    sandbox_dangerous_commands: int = 19
    sandbox_malicious_patterns: int = 31

    # ── 灰度自愈 ──
    grayscale_canary_percentage: float = 0.1
    grayscale_batch_size: int = 5
    grayscale_observation_period_seconds: int = 300
    auto_rollback_enabled: bool = True

    # ── ReAct 引擎 ──
    react_max_iterations: int = 5
    react_high_risk_pause: bool = True

    # ── LLM 路由规则 ──
    llm_route_intent_parse_primary: str = "zhipu"
    llm_route_intent_parse_fallback: str = "deepseek"
    llm_route_copilot_primary: str = "deepseek"
    llm_route_copilot_fallback: str = "zhipu"
    llm_route_config_generate_primary: str = "zhipu"
    llm_route_config_generate_fallback: str = "deepseek"
    llm_route_fault_diagnose_primary: str = "zhipu"
    llm_route_fault_diagnose_fallback: str = "deepseek"

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def database_url(self) -> str:
        if self.environment == "development":
            return "sqlite+aiosqlite:///./dev.db"
        return self.postgres_url

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()