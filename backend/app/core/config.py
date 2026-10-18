from functools import lru_cache
from pathlib import Path

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
    # Kimi 思考模式只接受 temperature=1，关闭思考只接受 0.6；确定性由工具与规则保证，而非温度
    llm_temperature: float = 1.0
    llm_temperature_no_thinking: float = 0.6
    llm_agent_thinking: bool = False  # 主 Agent 是否开启思考（关闭约快一倍）；话题路由始终关闭
    # 场景评估中出现过连接被重置：单次超时 30 秒、失败自动重试 2 次（指数退避），避免客户等待过久
    llm_timeout_seconds: float = 30
    llm_max_retries: int = 2

    agent_max_tool_calls: int = 6

    # 本地向量模型（fastembed）；更换模型若改变维度，需同步修改向量表迁移
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_query_instruction: str = "为这个句子生成表示以用于检索相关文章："

    # 本地语音识别（SenseVoice，经 sherpa-onnx 运行）：录音在本机转成文字，不发送给第三方，也不保存
    asr_model_dir: Path = Path(__file__).resolve().parents[2] / ".models/sensevoice-zh"
    asr_max_seconds: int = 60
    asr_threads: int = 2

    cors_origins: list[str] = ["http://localhost:3000"]

    # 演示身份：前端通过 X-Demo-User 请求头切换；demo_mode 允许一键清空演示数据
    demo_users: list[str] = ["demo_customer_1", "demo_customer_2"]
    # 演示用理财经理账号 → 理财经理编号（与客户基础画像中的 assigned_rm 对应）
    demo_rms: dict[str, str] = {"rm_li": "RM001", "rm_zhou": "RM002"}
    demo_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
