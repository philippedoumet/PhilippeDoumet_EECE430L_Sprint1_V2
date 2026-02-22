from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
import math

from .models import RateSnapshot

def _parse_iso(dt: str) -> datetime:
    if len(dt) == 16:
        dt = dt + ":00"
    d = datetime.fromisoformat(dt)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def record_snapshot(db: Session, buy: float, sell: float, mid: float) -> RateSnapshot:
    snap = RateSnapshot(
        buy_rate=buy,
        sell_rate=sell,
        mid_rate=mid,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap

def get_snapshots_in_range(db: Session, start: datetime, end: datetime) -> list[RateSnapshot]:
    stmt = (
        select(RateSnapshot)
        .where(RateSnapshot.created_at >= start)
        .where(RateSnapshot.created_at <= end)
        .order_by(RateSnapshot.created_at.asc())
    )
    return list(db.scalars(stmt).all())

def compute_rate_stats(snaps: list[RateSnapshot]) -> dict:
    mids = [s.mid_rate for s in snaps]
    if not mids:
        return {
            "count": 0, "min": None, "max": None, "avg": None,
            "first": None, "last": None, "percent_change": None,
            "std_dev": None, "trend_per_hour": None,
        }

    n = len(mids)
    mn = min(mids)
    mx = max(mids)
    avg = sum(mids) / n
    first = mids[0]
    last = mids[-1]

    percent_change = None
    if first != 0:
        percent_change = ((last - first) / first) * 100.0

    var = sum((x - avg) ** 2 for x in mids) / n
    std_dev = math.sqrt(var)

    t0 = snaps[0].created_at
    xs = []
    ys = mids
    for s in snaps:
        dt_hours = (s.created_at - t0).total_seconds() / 3600.0
        xs.append(dt_hours)

    x_avg = sum(xs) / n
    y_avg = avg
    denom = sum((x - x_avg) ** 2 for x in xs)
    if denom == 0:
        trend = 0.0
    else:
        numer = sum((xs[i] - x_avg) * (ys[i] - y_avg) for i in range(n))
        trend = numer / denom 

    return {
        "count": n, "min": mn, "max": mx, "avg": avg,
        "first": first, "last": last, "percent_change": percent_change,
        "std_dev": std_dev, "trend_per_hour": trend,
    }