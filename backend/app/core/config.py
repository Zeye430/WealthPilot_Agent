from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有配置来自环境变量或仓库根目录的 .env（不入库，参考 .env.example）。"""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://wealthpilot:wealthpilot@localhost:5433/wealthpilot"

    # Kimi（Moonshot）提供 OpenAI 兼容接口；换模型只改这三项
    llm_base_url: str = "https://api.moonshot.ai/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "kimi-k2.6"
    llm_temperature: float = 1.0  # kimi-k2.6 / kimi-k3 只接受 1；确定性由工具与规则保证，而非温度
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 1

    agent_max_tool_calls: int = 6

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
