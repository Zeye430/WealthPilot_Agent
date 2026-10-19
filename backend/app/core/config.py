from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有配置来自环境变量或仓库根目录的 .env（不入库，参考 .env.example）。"""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://wealthpilot:wealthpilot@localhost:5433/wealthpilot"
    # 连接池（P8-4 压测校准）：每进程最多 10 + 20 个连接；PostgreSQL 默认上限 100，
    # 多进程部署时保证「进程数 × 30」小于上限。等不到连接时 10 秒后返回 503，而不是让客户干等。
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: float = 10

    # Kimi（Moonshot）提供 OpenAI 兼容接口；换模型只改这三项
    llm_base_url: str = "https://api.moonshot.ai/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "kimi-k2.6"
    # Kimi 思考模式只接受 temperature=1，关闭思考只接受 0.6；确定性由工具与规则保证，而非温度
    llm_temperature: float = 1.0
    llm_temperature_no_thinking: float = 0.6
    llm_agent_thinking: bool = False  # 主 Agent 是否开启思考（关闭约快一倍）；话题路由始终关闭
    # 单次调用超时 25 秒、失败重试 1 次（场景评估中偶发连接重置，重试一次即可恢复）。
    # 与单轮时长上限、前端代理超时（120 秒）配合：最坏情况 ≈ 60 秒上限 + 一次调用 2×25 秒 < 120 秒
    llm_timeout_seconds: float = 25
    llm_max_retries: int = 1
    # 单轮对话时长上限：超过后不再调用模型，展示已查到的结果并说明（P8-4）
    chat_turn_budget_seconds: float = 60
    # 模型熔断：连续失败 5 次后暂停调用 30 秒，期间直接提示客户，之后放行一个探测请求
    llm_breaker_failures: int = 5
    llm_breaker_cooldown_seconds: float = 30
    # 费用估算单价（美元 / 百万 token）：kimi-k2.6 官网价格（2026-10 核对：输入未命中缓存 0.95、
    # 命中缓存 0.16、输出 4.00）。按未命中缓存计算，是费用上限；换模型时同步修改
    llm_price_input_per_mtok: float = 0.95
    llm_price_output_per_mtok: float = 4.00
    # 压测专用：fake 时用固定回复的假模型（模拟延迟），只测系统本身的吞吐，不调用、不计费
    llm_provider: str = "openai"
    fake_llm_latency_seconds: float = 1.5

    agent_max_tool_calls: int = 6

    # 本地向量模型（fastembed）；更换模型若改变维度，需同步修改向量表迁移
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_query_instruction: str = "为这个句子生成表示以用于检索相关文章："

    # 本地语音识别（SenseVoice，经 sherpa-onnx 运行）：录音在本机转成文字，不发送给第三方，也不保存
    asr_model_dir: Path = Path(__file__).resolve().parents[2] / ".models/sensevoice-zh"
    asr_max_seconds: int = 60
    asr_threads: int = 2

    # 允许的前端来源：CORS 与「跨站写请求」检查共用；部署时加入正式域名
    cors_origins: list[str] = ["http://localhost:3000"]

    # 登录与会话（服务端会话 + httpOnly Cookie）
    session_ttl_hours: int = 12  # 绝对有效期
    session_idle_minutes: int = 120  # 闲置超时
    cookie_secure: bool = False  # 部署到 HTTPS 时设为 true
    # 手机银行进入凭证（app ticket）：银行 App 签发、WealthPilot 核验的共享密钥与有效期。
    # 默认值只用于本地开发；部署时必须设置（生产中更推荐银行私钥签名、WealthPilot 公钥核验）
    app_ticket_secret: SecretStr = SecretStr("dev-only-app-ticket-secret-change-me")
    app_ticket_ttl_seconds: int = 60
    # 是否启用「模拟手机银行」（演示用，代表银行自己的系统，生产中不存在于本项目）
    bank_sim_enabled: bool = True

    # 公开演示访问码：设置后登录需要输入，防止陌生人刷模型额度；本地开发留空
    demo_access_code: SecretStr | None = None

    # 演示账号（启动时自动创建，密码统一为 demo_password；真实系统对接银行统一身份认证）
    demo_password: SecretStr = SecretStr("wealthpilot-demo")
    demo_accounts: list[dict] = [
        {
            "username": "wang",
            "display_name": "王先生（虚构）",
            "display_name_en": "Mr. Wang (fictional)",
            "role": "customer",
            "customer_id": "demo_customer_1",
        },
        {
            "username": "chen",
            "display_name": "陈女士（虚构）",
            "display_name_en": "Ms. Chen (fictional)",
            "role": "customer",
            "customer_id": "demo_customer_2",
        },
        {
            "username": "li",
            "display_name": "李经理（虚构）",
            "display_name_en": "RM Li (fictional)",
            "role": "rm",
            "rm_id": "RM001",
        },
        {
            "username": "ops",
            "display_name": "运维值班（虚构）",
            "display_name_en": "Ops on call (fictional)",
            "role": "ops",
        },
        {
            "username": "zhou",
            "display_name": "周经理（虚构）",
            "display_name_en": "RM Zhou (fictional)",
            "role": "rm",
            "rm_id": "RM002",
        },
    ]
    demo_mode: bool = True  # 允许客户一键清空自己的演示数据
    # 登录页显示的演示提示（如演示密码）；公开部署时配合访问码使用，或设为空不显示
    demo_login_hint: str | None = "演示账号的密码均为 wealthpilot-demo"
    demo_login_hint_en: str | None = "All demo accounts use the password wealthpilot-demo"

    # 可观测性：部署时设为 json（每行一个 JSON，便于云平台检索）；本地开发为可读文本
    log_format: str = "text"
    # Prometheus 指标接口 /metrics 的访问令牌；不设置时接口关闭（返回 404）
    metrics_token: SecretStr | None = None
    app_version: str = "0.8.0"
    git_sha: str = "dev"  # 部署时由 CI 注入，看板显示当前运行的版本

    # 限流（单实例内存滑动窗口；多实例部署时应换成 Redis）
    rate_limit_enabled: bool = True
    rate_limit_chat_per_minute: int = 20
    rate_limit_chat_per_day: int = 300
    rate_limit_speech_per_minute: int = 30
    rate_limit_login_per_minute: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
