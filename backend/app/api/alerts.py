from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Trend

router = APIRouter(prefix="/api", tags=["alerts"])


async def _get_pending_alerts(session: AsyncSession) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = await session.execute(
        select(Trend)
        .where(Trend.notified == 0, Trend.expires_at > now)
        .order_by(Trend.detected_at.desc())
    )
    trends = result.scalars().all()
    return [
        {
            "id": t.id,
            "topic": t.topic,
            "severity": t.severity,
            "story_count": t.story_count,
            "detected_at": t.detected_at,
            "expires_at": t.expires_at,
        }
        for t in trends
    ]


@router.get("/alerts/pending")
async def get_pending(session: AsyncSession = Depends(get_session)):
    return {"items": await _get_pending_alerts(session)}


@router.put("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, session: AsyncSession = Depends(get_session)):
    trend = await session.get(Trend, alert_id)
    if not trend:
        raise HTTPException(status_code=404, detail="Alert not found")
    trend.notified = 1
    await session.commit()
    return {"id": trend.id, "notified": True}
