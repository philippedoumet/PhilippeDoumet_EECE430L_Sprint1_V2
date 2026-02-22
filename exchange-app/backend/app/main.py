import time
import shutil
import os
import random
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pathlib import Path
import csv
import io

from .db import Base, engine, get_db
from .models import User, Transaction, UserPreference, ExchangeOffer, Trade, Alert, WatchlistItem, AuditLog, Notification, RateSnapshot
from .auth import hash_password, verify_password, create_access_token, get_current_user, get_current_admin
from .rate import fetch_unofficial_rate
from .stats import record_snapshot, compute_rate_stats, get_snapshots_in_range, _parse_iso
from .schemas import (
    RegisterIn, LoginIn, TokenOut, TransactionCreateIn, TransactionOut, RateOut,
    RateStatOut, RateSnapshotOut, UserOut, PreferenceSchema, SystemStatsOut,
    OfferCreateIn, AcceptOfferIn, OfferOut, TradeOut, AlertCreateIn, AlertOut,
    WatchlistCreateIn, WatchlistOut, AuditLogOut, NotificationOut, ReportOut, BackupStatusOut
)
from fastapi import BackgroundTasks
from .email_utils import send_alert_email, send_otp_email
from typing import Optional

app = FastAPI(title="USD↔LBP Exchange (Unofficial Rate)")

# ====================== RATE LIMITER ======================
request_counts = defaultdict(list)

def rate_limit(request: Request):
    client_ip = request.client.host
    current_time = time.time()
    request_counts[client_ip] = [t for t in request_counts[client_ip] if current_time - t < 60]
    
    if len(request_counts[client_ip]) >= 5:
        raise HTTPException(status_code=429, detail="Too Many Requests. Please try again in a minute.")
        
    request_counts[client_ip].append(current_time)

# ====================== DATABASE & STATIC ======================
Base.metadata.create_all(bind=engine)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

# ====================== HELPERS ======================
def log_audit(db: Session, user_id: Optional[int], action: str, details: str):
    log = AuditLog(user_id=user_id, action=action, details=details)
    db.add(log)
    db.commit()

def create_notification(db: Session, user_id: int, message: str):
    notif = Notification(user_id=user_id, message=message, is_read=False)
    db.add(notif)
    db.commit()

def verify_mfa_or_send_otp(user: User, db: Session, provided_otp: Optional[str]):
    """Handles generating, emailing, and verifying OTP codes."""
    if not user.mfa_enabled:
        return
    
    if not provided_otp:
        otp = str(random.randint(100000, 999999))
        user.current_otp = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=5)
        db.commit()
        send_otp_email(user.email, otp)
        raise HTTPException(status_code=403, detail="OTP required")
    
    if user.current_otp != provided_otp or user.otp_expiry is None or datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")
    
    # Clean up OTP after successful validation
    user.current_otp = None
    user.otp_expiry = None
    db.commit()

# ====================== AUTH ======================
@app.post("/api/auth/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    role = "ADMIN" if payload.is_admin else "USER"
    user = User(email=payload.email, password_hash=hash_password(payload.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)

    pref = UserPreference(user_id=user.id)
    db.add(pref)
    db.commit()

    token = create_access_token(user.id)
    return TokenOut(access_token=token)

@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db), _limiter: None = Depends(rate_limit)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        log_audit(db, user.id if user else None, "LOGIN_FAILED", f"Failed attempt for email: {payload.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # This will raise an error and pause the login if an OTP wasn't provided yet
    verify_mfa_or_send_otp(user, db, payload.otp)

    log_audit(db, user.id, "LOGIN_SUCCESS", "User logged in successfully")
    token = create_access_token(user.id)
    return TokenOut(access_token=token)

@app.get("/api/users/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user

@app.get("/api/preferences/me", response_model=PreferenceSchema)
def get_my_prefs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    return pref

@app.put("/api/preferences/me", response_model=PreferenceSchema)
def update_my_prefs(payload: PreferenceSchema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if pref:
        pref.time_range_days = payload.time_range_days
        pref.graph_interval = payload.graph_interval
    else:
        pref = UserPreference(user_id=user.id, **payload.dict())
        db.add(pref)
    db.commit()
    db.refresh(pref)
    log_audit(db, user.id, "PREFS_UPDATED", f"Updated defaults: {payload.time_range_days} days, {payload.graph_interval}")
    return pref

# ====================== RATE & ALERTS ======================
def check_and_trigger_alerts(db: Session, current_rate: float):
    active_alerts = db.query(Alert).filter(Alert.is_active == True).all()
    for alert in active_alerts:
        trigger = False
        if alert.condition == "ABOVE" and current_rate >= alert.target_rate:
            trigger = True
        elif alert.condition == "BELOW" and current_rate <= alert.target_rate:
            trigger = True
        
        if trigger:
            user = db.get(User, alert.user_id)
            if user:
                send_alert_email(user.email, current_rate, alert.target_rate, alert.condition)
                create_notification(db, user.id, f"ALERT TRIGGERED: Rate went {alert.condition} {alert.target_rate} LBP (Current: {current_rate})")
            
            alert.is_active = False
            db.commit()

@app.get("/api/rate", response_model=RateOut)
async def get_rate(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    buy, sell, mid = await fetch_unofficial_rate()
    record_snapshot(db, buy, sell, mid)
    background_tasks.add_task(check_and_trigger_alerts, db, mid)
    return RateOut(buy_rate=buy, sell_rate=sell, mid_rate=mid, source="rate.onrender.com")

# ====================== TRANSACTIONS ======================
@app.post("/api/transactions", response_model=TransactionOut)
async def create_transaction(
    payload: TransactionCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _limiter: None = Depends(rate_limit)
):
    verify_mfa_or_send_otp(user, db, payload.otp)

    buy, sell, mid = await fetch_unofficial_rate()
    record_snapshot(db, buy, sell, mid)
    rate_used = mid
    amount = float(payload.amount)

    if payload.direction == "USD_TO_LBP":
        amount_from = amount
        amount_to = amount * rate_used
        if user.usd_balance < amount_from:
            raise HTTPException(status_code=400, detail="Insufficient USD balance")
        user.usd_balance -= amount_from
        user.lbp_balance += amount_to
    else:  
        amount_from = amount
        amount_to = amount / rate_used
        if user.lbp_balance < amount_from:
            raise HTTPException(status_code=400, detail="Insufficient LBP balance")
        user.lbp_balance -= amount_from
        user.usd_balance += amount_to

    tx = Transaction(
        user_id=user.id,
        direction=payload.direction,
        amount_from=amount_from,
        amount_to=amount_to,
        rate_used=rate_used,
    )
    db.add(tx)
    db.commit() 
    db.refresh(tx)
    
    log_audit(db, user.id, "TRANSACTION_CREATED", f"Exchanged {amount_from} to {amount_to} (Rate: {rate_used})")
    return tx

@app.get("/api/transactions/me", response_model=list[TransactionOut])
def my_transactions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Transaction).filter(Transaction.user_id == user.id).order_by(Transaction.created_at.desc()).all()

@app.get("/api/transactions/export")
def export_transactions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txs = db.query(Transaction).filter(Transaction.user_id == user.id).order_by(Transaction.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Direction", "Amount From", "Amount To", "Rate Used"])
    for tx in txs:
        writer.writerow([tx.created_at.strftime("%Y-%m-%d %H:%M:%S"), tx.direction, tx.amount_from, tx.amount_to, tx.rate_used])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=transactions.csv"})

# ====================== P2P MARKETPLACE ======================
@app.post("/api/p2p/offers", response_model=OfferOut)
def create_offer(
    payload: OfferCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    verify_mfa_or_send_otp(user, db, payload.otp)
    
    amount = float(payload.amount)
    if payload.offer_type == "SELL_USD":
        if user.usd_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient USD balance to create offer")
        user.usd_balance -= amount
    else:
        if user.lbp_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient LBP balance to create offer")
        user.lbp_balance -= amount

    offer = ExchangeOffer(
        maker_user_id=user.id,
        offer_type=payload.offer_type,
        amount=amount,
        rate_lbp_per_usd=float(payload.rate_lbp_per_usd),
        status="OPEN",
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    log_audit(db, user.id, "OFFER_CREATED", f"Created {payload.offer_type} offer for {payload.amount}")
    return offer

@app.get("/api/p2p/offers/open", response_model=list[OfferOut])
def list_open_offers(db: Session = Depends(get_db)):
    return db.query(ExchangeOffer).filter(ExchangeOffer.status == "OPEN").order_by(ExchangeOffer.created_at.desc()).all()

@app.get("/api/p2p/me/offers", response_model=list[OfferOut])
def my_offers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ExchangeOffer).filter(ExchangeOffer.maker_user_id == user.id).order_by(ExchangeOffer.created_at.desc()).all()

@app.post("/api/p2p/offers/{offer_id}/cancel", response_model=OfferOut)
def cancel_offer(offer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    offer = db.get(ExchangeOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.maker_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own offer")
    if offer.status != "OPEN":
        raise HTTPException(status_code=400, detail="Only OPEN offers can be cancelled")

    if offer.offer_type == "SELL_USD":
        user.usd_balance += offer.amount
    else:
        user.lbp_balance += offer.amount

    offer.status = "CANCELLED"
    db.commit()
    db.refresh(offer)
    
    log_audit(db, user.id, "OFFER_CANCELLED", f"Cancelled offer #{offer.id}")
    create_notification(db, user.id, f"You cancelled your offer #{offer.id}. Funds refunded.")
    return offer

@app.post("/api/p2p/offers/{offer_id}/accept", response_model=TradeOut)
def accept_offer(
    offer_id: int,
    payload: AcceptOfferIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _limiter: None = Depends(rate_limit)
):
    verify_mfa_or_send_otp(user, db, payload.otp)

    offer = db.query(ExchangeOffer).with_for_update().filter(ExchangeOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "OPEN":
        raise HTTPException(status_code=400, detail="Offer is no longer open")
    if offer.maker_user_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot accept your own offer")

    rate = float(offer.rate_lbp_per_usd)
    amount = float(offer.amount)

    if offer.offer_type == "SELL_USD":
        maker_gives_amount = amount
        maker_gives_currency = "USD"
        maker_gets_amount = amount * rate
        maker_gets_currency = "LBP"
    else:
        maker_gives_amount = amount
        maker_gives_currency = "LBP"
        maker_gets_amount = amount / rate
        maker_gets_currency = "USD"

    if maker_gets_currency == "USD" and user.usd_balance < maker_gets_amount:
        raise HTTPException(status_code=400, detail="Insufficient USD to accept this offer")
    if maker_gets_currency == "LBP" and user.lbp_balance < maker_gets_amount:
        raise HTTPException(status_code=400, detail="Insufficient LBP to accept this offer")

    if maker_gets_currency == "USD":
        user.usd_balance -= maker_gets_amount
        offer.maker.usd_balance += maker_gets_amount
    else:
        user.lbp_balance -= maker_gets_amount
        offer.maker.lbp_balance += maker_gets_amount

    if maker_gives_currency == "USD":
        user.usd_balance += maker_gives_amount
    else:
        user.lbp_balance += maker_gives_amount

    offer.status = "FILLED"
    offer.filled_at = datetime.utcnow()

    trade = Trade(
        offer_id=offer.id, maker_user_id=offer.maker_user_id, taker_user_id=user.id,
        offer_type=offer.offer_type, maker_gives_amount=maker_gives_amount,
        maker_gives_currency=maker_gives_currency, maker_gets_amount=maker_gets_amount,
        maker_gets_currency=maker_gets_currency, rate_lbp_per_usd=rate,
    )
    db.add(trade)
    db.commit() 
    db.refresh(trade)
    
    log_audit(db, user.id, "OFFER_ACCEPTED", f"Accepted offer #{offer.id}, Trade #{trade.id} created")
    create_notification(db, offer.maker_user_id, f"SUCCESS: Your offer #{offer.id} was accepted! Trade #{trade.id} completed.")
    create_notification(db, user.id, f"SUCCESS: You accepted offer #{offer.id}. Trade #{trade.id} completed.")
    return trade

@app.get("/api/p2p/me/trades", response_model=list[TradeOut])
def my_trades(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Trade).filter(or_(Trade.maker_user_id == user.id, Trade.taker_user_id == user.id)).order_by(Trade.created_at.desc()).all()

# ====================== ALERTS & WATCHLIST ======================
@app.post("/api/alerts", response_model=AlertOut)
def create_alert(payload: AlertCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    alert = Alert(user_id=user.id, target_rate=payload.target_rate, condition=payload.condition, is_active=True)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    log_audit(db, user.id, "ALERT_CREATED", f"Set {payload.condition} alert for {payload.target_rate}")
    return alert

@app.get("/api/alerts/me", response_model=list[AlertOut])
def get_my_alerts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Alert).filter(Alert.user_id == user.id).order_by(Alert.created_at.desc()).all()

@app.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    alert = db.get(Alert, alert_id)
    if not alert or alert.user_id != user.id: raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return {"detail": "Alert deleted"}

@app.post("/api/watchlist", response_model=WatchlistOut)
def add_to_watchlist(payload: WatchlistCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = WatchlistItem(user_id=user.id, item_type=payload.item_type, value=payload.value, note=payload.note)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.get("/api/watchlist/me", response_model=list[WatchlistOut])
def get_my_watchlist(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id).order_by(WatchlistItem.created_at.desc()).all()

@app.delete("/api/watchlist/{item_id}")
def delete_watchlist_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.get(WatchlistItem, item_id)
    if not item or item.user_id != user.id: raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"detail": "Watchlist item deleted"}

# ====================== LOGS & NOTIFICATIONS ======================
@app.get("/api/logs/me", response_model=list[AuditLogOut])
def get_my_logs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(AuditLog).filter(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).all()

@app.get("/api/notifications/me", response_model=list[NotificationOut])
def get_my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).all()

@app.put("/api/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notif = db.get(Notification, notif_id)
    if not notif or notif.user_id != user.id: raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    db.commit()
    return {"detail": "Marked as read"}

@app.delete("/api/notifications/{notif_id}")
def delete_notification(notif_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notif = db.get(Notification, notif_id)
    if not notif or notif.user_id != user.id: raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(notif)
    db.commit()
    return {"detail": "Notification deleted"}

# ====================== ADMIN ENDPOINTS ======================
@app.get("/api/admin/users", response_model=list[UserOut])
def admin_get_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(User).all()

@app.put("/api/admin/users/{user_id}/status")
def admin_update_user_status(user_id: int, status: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    target = db.get(User, user_id)
    if not target: raise HTTPException(status_code=404, detail="User not found")
    target.status = status
    db.commit()
    return {"detail": f"User status updated to {status}"}

@app.get("/api/admin/stats", response_model=SystemStatsOut)
def admin_get_stats(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    total_users = db.query(User).count()
    total_txs = db.query(Transaction).count()
    usd_to_lbp = db.query(func.sum(Transaction.amount_from)).filter(Transaction.direction == "USD_TO_LBP").scalar() or 0
    lbp_to_usd = db.query(func.sum(Transaction.amount_to)).filter(Transaction.direction == "LBP_TO_USD").scalar() or 0
    return SystemStatsOut(total_users=total_users, total_transactions=total_txs, total_volume_usd=usd_to_lbp + lbp_to_usd)

@app.get("/api/admin/logs", response_model=list[AuditLogOut])
def admin_get_logs(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()

@app.get("/api/admin/reports", response_model=ReportOut)
def admin_reports(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    open_c = db.query(ExchangeOffer).filter(ExchangeOffer.status == "OPEN").count()
    filled_c = db.query(ExchangeOffer).filter(ExchangeOffer.status == "FILLED").count()
    canc_c = db.query(ExchangeOffer).filter(ExchangeOffer.status == "CANCELLED").count()
    
    txs = db.query(Transaction).all()
    vol = sum(t.amount_from if t.direction == "USD_TO_LBP" else t.amount_to for t in txs)
    
    top = db.query(Transaction.user_id, func.count(Transaction.id).label('c')) \
        .group_by(Transaction.user_id).order_by(func.count(Transaction.id).desc()).limit(5).all()
    
    active_users = []
    for uid, count in top:
        u = db.get(User, uid)
        if u:
            active_users.append({"email": u.email, "transactions": count})
            
    return ReportOut(
        total_usd_volume=vol,
        offers_open=open_c,
        offers_filled=filled_c,
        offers_cancelled=canc_c,
        most_active_users=active_users
    )

DB_PATH = "./exchange.db"
BACKUP_PATH = "./exchange_backup.db"

@app.post("/api/admin/backup")
def trigger_backup(admin: User = Depends(get_current_admin)):
    try:
        shutil.copy(DB_PATH, BACKUP_PATH)
        return {"detail": "Backup created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")

@app.post("/api/admin/restore")
def restore_backup(admin: User = Depends(get_current_admin)):
    if not os.path.exists(BACKUP_PATH):
        raise HTTPException(status_code=404, detail="No backup file found")
    try:
        shutil.copy(BACKUP_PATH, DB_PATH)
        return {"detail": "Restore successful. Please restart server."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")

@app.get("/api/admin/backup/status", response_model=BackupStatusOut)
def check_backup_status(admin: User = Depends(get_current_admin)):
    if os.path.exists(BACKUP_PATH):
        mtime = os.path.getmtime(BACKUP_PATH)
        return BackupStatusOut(status="Available", last_backup=datetime.fromtimestamp(mtime).isoformat())
    return BackupStatusOut(status="Not Found", last_backup=None)