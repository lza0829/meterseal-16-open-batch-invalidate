from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import connect
from app.services.gate import assert_period_writable_conn, write_tx
from app.services.reconcile_service import invalidate_batches_on_load

router = APIRouter(tags=["readings"])


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EstimateIn(BaseModel):
    meter_id: str
    period_id: str
    qty: float
    doc_no: str = Field(min_length=1)


class ActualIn(BaseModel):
    meter_id: str
    period_id: str
    qty: float
    occurred_at: str
    reader_code: str = "R00"
    doc_no: str = Field(min_length=1)


@router.get("/estimates")
def list_estimates(period_id: str | None = None):
    conn = connect()
    try:
        if period_id:
            rows = conn.execute(
                "SELECT * FROM estimates WHERE period_id=? ORDER BY meter_id", (period_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM estimates ORDER BY period_id, meter_id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _write_reading(
    conn: sqlite3.Connection,
    table: str,
    id_col: str,
    prefix: str,
    columns: list[str],
    values: list,
    period_id: str,
    fail_label: str,
) -> str:
    rid = prefix + uuid.uuid4().hex[:10]
    try:
        conn.execute(
            f"INSERT INTO {table}({id_col},{','.join(columns)}) VALUES (?,{','.join('?' * len(columns))})",
            [rid, *values],
        )
    except Exception as e:
        raise HTTPException(409, f"{fail_label}写入失败: {e}") from e
    # 装载成功即在同一事务里跑批失效钩子：绝不允许「已写数却仍留着旧 open 批」
    hook = invalidate_batches_on_load(conn, period_id)
    return rid, hook


@router.post("/estimates")
def create_estimate(body: EstimateIn):
    with write_tx() as conn:
        assert_period_writable_conn(conn, body.period_id)
        mid = conn.execute("SELECT 1 FROM meters WHERE meter_id=?", (body.meter_id,)).fetchone()
        if not mid:
            raise HTTPException(404, "表具不存在")
        eid, hook = _write_reading(
            conn,
            "estimates",
            "estimate_id",
            "E-",
            ["meter_id", "period_id", "qty", "doc_no", "loaded_at"],
            [body.meter_id, body.period_id, body.qty, body.doc_no, _now()],
            body.period_id,
            "估抄",
        )
        return {"estimate_id": eid, "ok": True, **hook}


@router.get("/actuals")
def list_actuals(period_id: str | None = None):
    conn = connect()
    try:
        if period_id:
            rows = conn.execute(
                "SELECT * FROM actuals WHERE period_id=? ORDER BY meter_id", (period_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM actuals ORDER BY period_id, meter_id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/actuals")
def create_actual(body: ActualIn):
    with write_tx() as conn:
        assert_period_writable_conn(conn, body.period_id)
        mid = conn.execute("SELECT 1 FROM meters WHERE meter_id=?", (body.meter_id,)).fetchone()
        if not mid:
            raise HTTPException(404, "表具不存在")
        aid, hook = _write_reading(
            conn,
            "actuals",
            "actual_id",
            "A-",
            ["meter_id", "period_id", "qty", "occurred_at", "reader_code", "doc_no", "loaded_at"],
            [
                body.meter_id,
                body.period_id,
                body.qty,
                body.occurred_at,
                body.reader_code,
                body.doc_no,
                _now(),
            ],
            body.period_id,
            "实抄",
        )
        return {"actual_id": aid, "ok": True, **hook}
