from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base
from sqlalchemy import Float, DateTime
from datetime import timezone
from sqlalchemy import Boolean
from typing import Optional

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    
    role: Mapped[str] = mapped_column(String, default="USER") 
    status: Mapped[str] = mapped_column(String, default="ACTIVE") 
    
    # NEW: MFA Fields
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=True) 
    current_otp: Mapped[str] = mapped_column(String, nullable=True)
    otp_expiry: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    usd_balance: Mapped[float] = mapped_column(Float, default=10000.0)
    lbp_balance: Mapped[float] = mapped_column(Float, default=1000000000.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")
    preferences: Mapped["UserPreference"] = relationship("UserPreference", uselist=False, back_populates="user")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)
    
    time_range_days: Mapped[int] = mapped_column(Integer, default=7)
    graph_interval: Mapped[str] = mapped_column(String, default="DAILY")

    user: Mapped["User"] = relationship(back_populates="preferences")

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # USD_TO_LBP or LBP_TO_USD

    amount_from: Mapped[float] = mapped_column(Float, nullable=False)
    amount_to: Mapped[float] = mapped_column(Float, nullable=False)
    rate_used: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="transactions")

class RateSnapshot(Base):
    __tablename__ = "rate_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buy_rate: Mapped[float] = mapped_column(Float, nullable=False)
    sell_rate: Mapped[float] = mapped_column(Float, nullable=False)
    mid_rate: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

class ExchangeOffer(Base):
    __tablename__ = "exchange_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    maker_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    offer_type: Mapped[str] = mapped_column(String, nullable=False)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    rate_lbp_per_usd: Mapped[float] = mapped_column(Float, nullable=False)

    status: Mapped[str] = mapped_column(String, default="OPEN", nullable=False)  # OPEN, CANCELLED, FILLED

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    maker: Mapped["User"] = relationship("User")

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    offer_id: Mapped[int] = mapped_column(Integer, ForeignKey("exchange_offers.id"), nullable=False, index=True)

    maker_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    taker_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    offer_type: Mapped[str] = mapped_column(String, nullable=False)

    maker_gives_amount: Mapped[float] = mapped_column(Float, nullable=False)
    maker_gives_currency: Mapped[str] = mapped_column(String, nullable=False)  # "USD" or "LBP"

    maker_gets_amount: Mapped[float] = mapped_column(Float, nullable=False)
    maker_gets_currency: Mapped[str] = mapped_column(String, nullable=False)  # "USD" or "LBP"

    rate_lbp_per_usd: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    offer: Mapped["ExchangeOffer"] = relationship("ExchangeOffer")

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    target_rate: Mapped[float] = mapped_column(Float, nullable=False)
    condition: Mapped[str] = mapped_column(String, nullable=False) 
    is_active: Mapped[bool] = mapped_column(Boolean, default=True) 
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")

class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    item_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    message: Mapped[str] = mapped_column(String, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")