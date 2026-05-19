from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    """
    应用配置类
    
    从环境变量或.env文件读取配置
    """
    # API Keys
    openai_api_key: str = ""
    dashscope_api_key: str = ""
    
    # Application Settings
    app_name: str = "ComputeNetworkAgentHub"
    app_env: str = "development"
    log_level: str = "INFO"
    
    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Streamlit Settings
    streamlit_port: int = 8501
    
    # Simulator Settings
    simulator_host: str = "0.0.0.0"
    simulator_port: int = 8080
    
    # Workflow Settings
    max_retries: int = 3
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8"
    )

# 全局配置实例
settings = Settings()