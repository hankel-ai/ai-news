import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Setting
from app.scheduler import reschedule_from_db

router = APIRouter(prefix="/api", tags=["settings"])

DEFAULTS = {
    "fetch_interval_minutes": "60",
    "retention_days": "30",
    "enrich_content": "false",
    "display_group_by_date": "true",
    "display_page_size": "50",
    "max_stories_per_fetch": "100",
    "timezone": "America/New_York",
}


def _parse_value(raw: str) -> str | int | bool:
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


async def _get_all(session: AsyncSession) -> dict:
    rows = (await session.execute(select(Setting))).scalars().all()
    current = {r.key: r.value for r in rows}
    merged = {k: current.get(k, v) for k, v in DEFAULTS.items()}
    merged.update({k: v for k, v in current.items() if k not in DEFAULTS})
    return {k: _parse_value(v) for k, v in merged.items()}


@router.get("/settings")
async def get_settings(session: AsyncSession = Depends(get_session)):
    return await _get_all(session)


@router.put("/settings")
async def update_settings(body: dict, session: AsyncSession = Depends(get_session)):
    needs_reschedule = False
    for key, value in body.items():
        str_val = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        existing = await session.get(Setting, key)
        if existing:
            if key == "fetch_interval_minutes" and existing.value != str_val:
                needs_reschedule = True
            existing.value = str_val
        else:
            if key == "fetch_interval_minutes":
                needs_reschedule = True
            session.add(Setting(key=key, value=str_val))
    await session.commit()

    if needs_reschedule:
        await reschedule_from_db()

    return await _get_all(session)
