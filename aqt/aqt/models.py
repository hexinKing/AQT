import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


def _now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    email = Column(String(128), nullable=False, default="")
    smtp_host = Column(String(128), default="smtp.qq.com")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(128), default="")
    smtp_password = Column(String(128), default="")
    created_at = Column(DateTime, default=_now)

    watchlist = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="user", cascade="all, delete-orphan")
    notification_logs = relationship("NotificationLog", back_populates="user", cascade="all, delete-orphan")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(16), nullable=False)
    name = Column(String(64), default="")
    strategy_params = Column(Text, default="{}")  # JSON
    added_at = Column(DateTime, default=_now)

    user = relationship("User", back_populates="watchlist")

    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),)

    @property
    def strategies(self) -> dict:
        return json.loads(self.strategy_params)

    @strategies.setter
    def strategies(self, val: dict):
        self.strategy_params = json.dumps(val, ensure_ascii=False)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(16), nullable=False)
    shares = Column(Integer, nullable=False, default=0)
    avg_cost = Column(Float, nullable=False, default=0.0)
    note = Column(String(256), default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    user = relationship("User", back_populates="positions")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(16), nullable=False)
    strategy = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)  # BUY / SELL
    price = Column(Float, nullable=True)
    reason = Column(String(512), default="")
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)

    user = relationship("User", back_populates="signals")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ntype = Column(String(16), nullable=False)  # email / sms / web
    recipient = Column(String(128), default="")
    subject = Column(String(256), default="")
    body_snippet = Column(String(256), default="")
    success = Column(Integer, default=0)  # 0 = fail, 1 = success
    error_msg = Column(String(256), default="")
    created_at = Column(DateTime, default=_now)

    user = relationship("User", back_populates="notification_logs")
