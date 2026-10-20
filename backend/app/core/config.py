from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables or .env at the repo root (not committed; see
    .env.example)."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://wealthpilot:wealthpilot@localhost:5433/wealthpilot"
    # Connection pool (tuned by P8-4 load tests): up to 10 + 20 connections per process;
    # PostgreSQL's default limit is 100,
    # so with several processes keep processes × 30 below it. If no connection is free within 10
    # seconds, return 503 instead of making customers wait.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: float = 10

    # Kimi (Moonshot) offers an OpenAI-compatible API; switching models only changes these three
    llm_base_url: str = "https://api.moonshot.ai/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "kimi-k2.6"
    # Kimi thinking mode only accepts temperature=1, and non-thinking only 0.6; determinism comes
    # from tools and rules, not temperature
    llm_temperature: float = 1.0
    llm_temperature_no_thinking: float = 0.6
    # thinking for the main agent (off is about twice as fast); always off for the topic router
    llm_agent_thinking: bool = False
    # 25-second timeout per call with 1 retry (connection resets happened occasionally in scenario
    # evals; one retry recovers).
    # Fits with the turn budget and the frontend proxy timeout (120 s): worst case ≈ 60 s budget +
    # one call 2×25 s < 120 s
    llm_timeout_seconds: float = 25
    llm_max_retries: int = 1
    # Turn time budget: after it, stop calling the model and show what was already found, with an
    # explanation (P8-4)
    chat_turn_budget_seconds: float = 60
    # Model circuit breaker: after 5 consecutive failures, pause calls for 30 s and tell customers
    # directly, then let one probe through
    llm_breaker_failures: int = 5
    llm_breaker_cooldown_seconds: float = 30
    # Prices for cost estimates (USD per million tokens): kimi-k2.6 list prices (checked 2026-10:
    # input cache miss 0.95,
    # cache hit 0.16, output 4.00). Computed at cache-miss prices, so it's an upper bound; update
    # when switching models
    llm_price_input_per_mtok: float = 0.95
    llm_price_output_per_mtok: float = 4.00
    # Load testing only: fake uses a canned-reply model (with simulated latency) to measure the
    # system's own throughput, with no calls or cost
    llm_provider: str = "openai"
    fake_llm_latency_seconds: float = 1.5

    agent_max_tool_calls: int = 6

    # Local embedding model (fastembed); a model with a different dimension needs a matching
    # vector-table migration
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_query_instruction: str = "为这个句子生成表示以用于检索相关文章："
    # Embedding model cache directory; if unset, fastembed's default temp directory is used
    # (re-downloaded after a container rebuild). Mount a persistent volume in production
    embedding_cache_dir: Path | None = None
    # Warm up in the background at startup: load the embedding model and sync the search index so
    # the first customer doesn't wait
    # (on in production; off by default in tests and development)
    warmup_on_start: bool = False

    # Local speech recognition (SenseVoice via sherpa-onnx): audio is transcribed on this server,
    # never sent to third parties or stored
    asr_model_dir: Path = Path(__file__).resolve().parents[2] / ".models/sensevoice-zh"
    asr_max_seconds: int = 60
    asr_threads: int = 2

    # Allowed frontend origins: shared by CORS and the cross-site write check; add the real domain
    # when deploying
    cors_origins: list[str] = ["http://localhost:3000"]

    # Sign-in and sessions (server-side sessions + httpOnly cookie)
    session_ttl_hours: int = 12  # absolute lifetime
    session_idle_minutes: int = 120  # idle timeout
    cookie_secure: bool = False  # set to true behind HTTPS
    # Mobile banking entry ticket (app ticket): shared secret and lifetime, issued by the bank app
    # and verified by WealthPilot.
    # The default is for local development only and must be set when deploying (in production,
    # prefer bank private-key signing with WealthPilot verifying by public key)
    app_ticket_secret: SecretStr = SecretStr("dev-only-app-ticket-secret-change-me")
    app_ticket_ttl_seconds: int = 60
    # Whether the simulated mobile banking app is enabled (demo only; stands in for the bank's own
    # system, which isn't part of this project in production)
    bank_sim_enabled: bool = True

    # Public demo access code: when set, sign-in requires it so strangers can't burn model credits;
    # leave empty for local development
    demo_access_code: SecretStr | None = None

    # Demo accounts (created at startup, all with demo_password; a real system would use the bank's
    # single sign-on)
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
    demo_mode: bool = True  # lets customers clear their own demo data
    # Demo hint on the sign-in page (e.g. the demo password); for public deployments use with an
    # access code, or leave empty to hide it
    demo_login_hint: str | None = "演示账号的密码均为 wealthpilot-demo"
    demo_login_hint_en: str | None = "All demo accounts use the password wealthpilot-demo"

    # Observability: set to json when deploying (one JSON object per line, easy to search in cloud
    # logging); readable text locally
    log_format: str = "text"
    # Access token for the Prometheus /metrics endpoint; if unset, the endpoint is off (returns 404)
    metrics_token: SecretStr | None = None
    app_version: str = "0.8.0"
    git_sha: str = "dev"  # injected by CI when deploying; the dashboard shows the running version

    # Rate limits (in-memory sliding window per instance; use Redis for multiple instances)
    rate_limit_enabled: bool = True
    rate_limit_chat_per_minute: int = 20
    rate_limit_chat_per_day: int = 300
    rate_limit_speech_per_minute: int = 30
    rate_limit_login_per_minute: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
