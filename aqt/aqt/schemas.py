from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# ── Auth ──
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


# ── Watchlist ──
class WatchlistCreate(BaseModel):
    symbol: str
    name: str = ""


class WatchlistOut(BaseModel):
    id: int
    symbol: str
    name: str
    strategy_params: str
    added_at: datetime

    class Config:
        from_attributes = True


# ── Position ──
class PositionCreate(BaseModel):
    symbol: str
    shares: int
    avg_cost: float
    note: str = ""


class PositionUpdate(BaseModel):
    shares: Optional[int] = None
    avg_cost: Optional[float] = None
    note: Optional[str] = None


class PositionOut(BaseModel):
    id: int
    symbol: str
    shares: int
    avg_cost: float
    note: str
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Signal ──
class SignalOut(BaseModel):
    id: int
    symbol: str
    strategy: str
    direction: str
    price: Optional[float]
    reason: str
    is_read: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Settings ──
class SettingsUpdate(BaseModel):
    email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None


class SettingsOut(BaseModel):
    email: str
    smtp_host: str
    smtp_port: int
    smtp_user: str


# ── Generic ──
class ApiResponse(BaseModel):
    ok: bool
    data: Optional[object] = None
    error: Optional[str] = None
