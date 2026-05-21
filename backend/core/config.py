from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NetOps_Intent_System"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "netops_db"
    postgres_user: str = "netops_user"
    postgres_password: str = "netops_password"

    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = ""
    influxdb_org: str = "netops"
    influxdb_bucket: str = "telemetry"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"
    llm_max_tokens: int = 4096
    llm_timeout: int = 30

    secret_key: str = ""
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 500

    device_connect_timeout: int = 10
    device_read_timeout: int = 30

    change_window_start: str = "08:00"
    change_window_end: str = "22:00"

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()