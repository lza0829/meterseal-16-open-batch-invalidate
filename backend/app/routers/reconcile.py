from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect
from app.services import reconcile_service

router = APIRouter(tags=["reconcile"])


class AlignIn(BaseModel):
    period_id: str


class SealIn(BaseModel):
    period_id: str
    batch_id: str | None = None
    acknowledge_stale: bool = False


class FateIn(BaseModel):
    fate: str


class InvalidateIn(BaseModel):
    reason: str = "manual"


@router.post("/align")
def align(body: AlignIn):
    return reconcile_service.run_align(body.period_id)


@router.get("/batches")
def batches(period_id: str | None = None):
    conn = connect()
    try:
        if period_id:
            view = reconcile_service.current_batch_view(conn, period_id)
            return view["batches"]
        mode = reconcile_service.read_invalidation_mode(conn)
        out = []
        for p in conn.execute("SELECT period_id FROM periods ORDER BY period_id DESC").fetchall():
            pid = p["period_id"]
            watermark = reconcile_service.period_load_watermark(conn, pid)
            signature = reconcile_service.source_signature(conn, pid)
            rows = conn.execute(
                "SELECT * FROM reconcile_batches WHERE period_id=? ORDER BY created_at DESC",
                (pid,),
            ).fetchall()
            out.extend(
                reconcile_service.decorate_batch(r, watermark, mode, signature) for r in rows
            )
        return out
    finally:
        conn.close()


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str):
    conn = connect()
    try:
        batch = conn.execute(
            "SELECT * FROM reconcile_batches WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if not batch:
            raise HTTPException(404, "对账批不存在")
        view = reconcile_service.current_batch_view(conn, batch["period_id"])
        detail = next(
            (b for b in view["batches"] if b["batch_id"] == batch_id),
            reconcile_service.decorate_batch(
                batch, view["load_watermark"], view["invalidation_mode"]
            ),
        )
        return {
            **detail,
            "load_watermark": view["load_watermark"],
            "can_seal": detail["usability"] == "usable"
            or (detail["invalidation_mode"] == "manual" and detail["usability"] == "stale"),
            "period_status": conn.execute(
                "SELECT status FROM periods WHERE period_id=?", (batch["period_id"],)
            ).fetchone()["status"],
        }
    finally:
        conn.close()


@router.post("/batches/{batch_id}/invalidate")
def invalidate_batch(batch_id: str, body: InvalidateIn | None = None):
    reason = (body.reason if body else None) or "manual"
    return reconcile_service.invalidate_batch(batch_id, reason=reason, actor="manual")


@router.get("/variances")
def variances(batch_id: str | None = None, period_id: str | None = None):
    conn = connect()
    try:
        if batch_id:
            rows = conn.execute(
                "SELECT * FROM variances WHERE batch_id=? ORDER BY meter_id", (batch_id,)
            ).fetchall()
        elif period_id:
            rows = conn.execute(
                "SELECT * FROM variances WHERE period_id=? ORDER BY meter_id", (period_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM variances ORDER BY period_id, meter_id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/variances/{variance_id}/fate")
def set_fate(variance_id: str, body: FateIn):
    return reconcile_service.set_fate(variance_id, body.fate)


@router.post("/seal")
def seal(body: SealIn):
    return reconcile_service.seal_period(
        body.period_id, body.batch_id, body.acknowledge_stale
    )


@router.get("/periods")
def periods():
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM periods ORDER BY period_id DESC").fetchall()]
    finally:
        conn.close()
