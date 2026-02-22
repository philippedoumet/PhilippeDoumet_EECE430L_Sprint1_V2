from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional, List
from datetime import datetime

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    is_admin: bool = False  

class LoginIn(BaseModel):
    email: EmailStr
    password: str
    otp: Optional[str] = None # Added for MFA

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

Direction = Literal["USD_TO_LBP", "LBP_TO_USD"]

class TransactionCreateIn(BaseModel):
    direction: Direction
    amount: float = Field(gt=0) 
    otp: Optional[str] = None # Added for MFA

class TransactionOut(BaseModel):
    id: int
    direction: str
    amount_from: float
    amount_to: float
    rate_used: float
    created_at: datetime

    class Config:
        from_attributes = True

class RateOut(BaseModel):
    buy_rate: float
    sell_rate: float
    mid_rate: float
    source: str

class RateStatOut(BaseModel):
    count: int
    min: Optional[float]
    max: Optional[float]   
    avg: Optional[float]
    first: Optional[float]
    last: Optional[float]
    percent_change: Optional[float]
    std_dev: Optional[float]
    trend_per_hour: Optional[float]

class RateSnapshotOut(BaseModel):
    created_at: datetime
    mid_rate: float

    class Config:
        from_attributes = True

class OfferCreateIn(BaseModel):
    offer_type: str
    amount: float = Field(gt=0) 
    rate_lbp_per_usd: float = Field(gt=0) 
    otp: Optional[str] = None # Added for MFA

class AcceptOfferIn(BaseModel):
    otp: Optional[str] = None # Added for MFA

class OfferOut(BaseModel):
    id: int
    maker_user_id: int
    offer_type: str
    amount: float
    rate_lbp_per_usd: float
    status: str
    created_at: datetime
    filled_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TradeOut(BaseModel):
    id: int
    offer_id: int
    maker_user_id: int
    taker_user_id: int
    offer_type: str
    maker_gives_amount: float
    maker_gives_currency: str
    maker_gets_amount: float
    maker_gets_currency: str
    rate_lbp_per_usd: float
    created_at: datetime

    class Config:
        from_attributes = True

class AlertCreateIn(BaseModel):
    target_rate: float = Field(gt=0) 
    condition: Literal["ABOVE", "BELOW"]

class AlertOut(BaseModel):
    id: int
    target_rate: float
    condition: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class WatchlistCreateIn(BaseModel):
    item_type: Literal["THRESHOLD", "DIRECTION"]
    value: str
    note: Optional[str] = None

class WatchlistOut(BaseModel):
    id: int
    item_type: str
    value: str
    note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class UserOut(BaseModel):
    id: int
    email: str
    role: str
    status: str
    usd_balance: float
    lbp_balance: float
    
    class Config:
        from_attributes = True

class PreferenceSchema(BaseModel):
    time_range_days: int
    graph_interval: str
    
    class Config:
        from_attributes = True

class SystemStatsOut(BaseModel):
    total_users: int
    total_transactions: int
    total_volume_usd: float

class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    details: str
    created_at: datetime

    class Config:
        from_attributes = True

class NotificationOut(BaseModel):
    id: int
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ReportOut(BaseModel):
    total_usd_volume: float
    offers_open: int
    offers_filled: int
    offers_cancelled: int
    most_active_users: List[dict]

class BackupStatusOut(BaseModel):
    status: str
    last_backup: Optional[str]