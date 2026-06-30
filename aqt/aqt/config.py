import os
from dataclasses import dataclass


@dataclass
class Settings:
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 168  # 7 days

    # SMTP defaults (QQ mail)
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            jwt_secret=os.getenv("JWT_SECRET", cls.jwt_secret),
            jwt_expire_hours=int(os.getenv("JWT_EXPIRE_HOURS", str(cls.jwt_expire_hours))),
            smtp_host=os.getenv("SMTP_HOST", cls.smtp_host),
            smtp_port=int(os.getenv("SMTP_PORT", str(cls.smtp_port))),
            smtp_user=os.getenv("SMTP_USER", cls.smtp_user),
            smtp_password=os.getenv("SMTP_PASSWORD", cls.smtp_password),
        )


settings = Settings.from_env()
