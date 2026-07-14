import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 168  # 7 days

    # SMTP defaults (QQ mail)
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Phase 1 integrations
    news_cache_ttl: int = 120
    news_http_timeout: int = 5
    market_close_report_time: str = "15:05"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            jwt_secret=os.getenv("JWT_SECRET", cls.jwt_secret),
            jwt_expire_hours=int(os.getenv("JWT_EXPIRE_HOURS", str(cls.jwt_expire_hours))),
            smtp_host=os.getenv("SMTP_HOST", cls.smtp_host),
            smtp_port=int(os.getenv("SMTP_PORT", str(cls.smtp_port))),
            smtp_user=os.getenv("SMTP_USER", cls.smtp_user),
            smtp_password=os.getenv("SMTP_PASSWORD", cls.smtp_password),
            news_cache_ttl=int(os.getenv("NEWS_CACHE_TTL", str(cls.news_cache_ttl))),
            news_http_timeout=int(os.getenv("NEWS_HTTP_TIMEOUT", str(cls.news_http_timeout))),
            market_close_report_time=os.getenv("MARKET_CLOSE_REPORT_TIME", cls.market_close_report_time),
        )


settings = Settings.from_env()
