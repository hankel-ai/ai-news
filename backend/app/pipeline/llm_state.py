"""LLM outage state, persisted in the settings KV table so it survives restarts.

One JSON row, key `llm_outage_state`:
    {"outage": true, "since": iso, "reason": str, "last_probe_at": iso, "skipped_runs": int}
No row (or outage=false) means the LLM is healthy.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting

logger = logging.getLogger(__name__)

STATE_KEY = "llm_outage_state"


async def _write(session: AsyncSession, state: dict | None) -> None:
    if state is None:
        existing = await session.get(Setting, STATE_KEY)
        if existing is not None:
            await session.delete(existing)
            await session.flush()  # emit DELETE now so later get() in same txn doesn't see stale identity-map row
        return
    existing = await session.get(Setting, STATE_KEY)
    if existing is not None:
        existing.value = json.dumps(state)
    else:
        session.add(Setting(key=STATE_KEY, value=json.dumps(state)))
    # note: commit happens with the caller's transaction


async def get_outage_state(session: AsyncSession) -> dict | None:
    row = await session.get(Setting, STATE_KEY)
    if row is None:
        return None
    try:
        state = json.loads(row.value)
    except json.JSONDecodeError:
        logger.warning("corrupt llm_outage_state row — treating as healthy")
        return None
    if not state.get("outage"):
        return None
    return state


async def record_outage(session: AsyncSession, reason: str) -> None:
    """Mark outage. If one is already recorded, update reason but keep since/skipped_runs."""
    existing = await get_outage_state(session)
    if existing:
        existing["outage"] = True
        existing["reason"] = reason[:500]
        await _write(session, existing)
    else:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        await _write(session, {
            "outage": True,
            "since": now,
            "reason": reason[:500],
            "last_probe_at": None,
            "skipped_runs": 0,
        })


async def clear_outage(session: AsyncSession) -> None:
    await _write(session, None)


async def record_probe(session: AsyncSession, ok: bool) -> None:
    """Update state after a probe. ok=True clears the outage; ok=False bumps skipped_runs."""
    state = await get_outage_state(session)
    if state is None:
        return
    if ok:
        await clear_outage(session)
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["last_probe_at"] = now
    state["skipped_runs"] = int(state.get("skipped_runs", 0)) + 1
    await _write(session, state)
