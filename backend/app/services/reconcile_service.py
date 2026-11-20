from __future__ import annotations
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.services.gate import (
    assert_period_writable_conn,
    read_invalidation_mode,
    write_tx,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- 账期装载水位

def source_signature(conn: sqlite3.Connection, period_id: str) -> str:
    """估抄/实抄的装载指纹：内容或装载时刻任一变化都要换值。

    比单看 MAX(loaded_at) 更严——同一秒内先对齐再装载，时刻相等也不会误判为未变。
    """
    parts = [period_id]
    for table, id_col in (("estimates", "estimate_id"), ("actuals", "actual_id")):
        for r in conn.execute(
            f"SELECT * FROM {table} WHERE period_id=? ORDER BY {id_col}", (period_id,)
        ).fetchall():
            parts.append(f"{r['meter_id']}:{r['qty']!r}:{r['doc_no']}:{r['loaded_at']}")
        parts.append("|")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def period_load_watermark(conn: sqlite3.Connection, period_id: str) -> str | None:
    """该账期估抄/实抄的最大装载时刻；批的 source_loaded_at 低于它即陈旧。"""
    row = conn.execute(
        """SELECT MAX(loaded_at) AS w FROM (
               SELECT loaded_at FROM estimates WHERE period_id=?
               UNION ALL
               SELECT loaded_at FROM actuals WHERE period_id=?
           )""",
        (period_id, period_id),
    ).fetchone()
    return row["w"] if row else None


def _is_stale(
    batch: sqlite3.Row | dict, watermark: str | None, signature: str | None = None
) -> bool:
    if not watermark:
        return False
    base = batch["source_loaded_at"] or batch["created_at"]
    if not base:
        return True
    if watermark > base:
        return True
    if signature is not None and batch["source_sig"] != signature:
        return True
    return False


def decorate_batch(
    batch: sqlite3.Row | dict,
    watermark: str | None,
    mode: str,
    signature: str | None = None,
) -> dict:
    """给前端/总览统一口径：批是否陈旧、能否直接封印。"""
    d = dict(batch)
    stale = d.get("status") == "open" and _is_stale(d, watermark, signature)
    d["is_stale"] = bool(stale)
    d["invalidation_mode"] = mode
    if d.get("status") == "expired":
        d["usability"] = "expired"
        d["stale_hint"] = "批已作废，须重跑对齐后才能封印"
    elif stale:
        d["usability"] = "stale"
        d["stale_hint"] = (
            "批已陈旧：装载成功后未重跑对齐，指纹可能不再代表现数据"
            if mode == "manual"
            else "批已陈旧：装载成功后未重跑对齐"
        )
    elif d.get("status") == "open":
        d["usability"] = "usable"
        d["stale_hint"] = ""
    else:
        d["usability"] = d.get("status") or ""
        d["stale_hint"] = ""
    return d


def current_batch_view(conn: sqlite3.Connection, period_id: str) -> dict:
    mode = read_invalidation_mode(conn)
    watermark = period_load_watermark(conn, period_id)
    signature = source_signature(conn, period_id)
    rows = conn.execute(
        "SELECT * FROM reconcile_batches WHERE period_id=? ORDER BY created_at DESC",
        (period_id,),
    ).fetchall()
    return {
        "period_id": period_id,
        "invalidation_mode": mode,
        "load_watermark": watermark,
        "batches": [decorate_batch(r, watermark, mode, signature) for r in rows],
    }


# ---------------------------------------------------------------- 装载钩子

def invalidate_batches_on_load(
    conn: sqlite3.Connection, period_id: str
) -> dict[str, Any]:
    """装载成功后的批失效钩子，必须与装载写入同事务调用。

    自动架构：把该账期全部 open 批置为 expired（不改 sealed 批）；
    人工架构：不改批态，仅提示哪些 open 批已陈旧。
    两架构都会给出提示，绝不静默沿用旧指纹。
    """
    mode = read_invalidation_mode(conn)
    watermark = period_load_watermark(conn, period_id)
    signature = source_signature(conn, period_id)
    open_rows = conn.execute(
        "SELECT * FROM reconcile_batches WHERE period_id=? AND status='open'",
        (period_id,),
    ).fetchall()

    if mode == "auto":
        now = _now()
        for b in open_rows:
            conn.execute(
                """UPDATE reconcile_batches
                      SET status='expired', invalidated_at=?, invalidated_reason='new_load'
                    WHERE batch_id=? AND status='open'""",
                (now, b["batch_id"]),
            )
        expired = [b["batch_id"] for b in open_rows]
        stale = []
        notice = (
            f"已装载；{len(expired)} 个开放批自动作废，须重跑对齐后再封印"
            if expired
            else "已装载；该账期当前无开放批，须重跑对齐"
        )
    else:
        expired = []
        stale = [b["batch_id"] for b in open_rows if _is_stale(b, watermark, signature)]
        if not open_rows:
            notice = "已装载；该账期无开放批，须重跑对齐后才能封印"
        elif stale:
            notice = f"已装载；{len(stale)} 个开放批可能陈旧，封印前请重跑对齐或人工作废"
        else:
            notice = "已装载；开放批仍绑定旧数据，封印前请重跑对齐或人工作废"

    return {
        "invalidation_mode": mode,
        "invalidated_batches": expired,
        "stale_batches": stale,
        "notice": notice,
        "needs_realign": bool(expired or stale),
    }


def invalidate_batch(
    batch_id: str, reason: str = "manual", actor: str = "manual"
) -> dict:
    """人工失效入口。两架构共用；已用其封印的账期不允许再改。"""
    with write_tx() as conn:
        batch = conn.execute(
            "SELECT * FROM reconcile_batches WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if not batch:
            raise HTTPException(404, "对账批不存在")
        period = conn.execute(
            "SELECT status FROM periods WHERE period_id=?", (batch["period_id"],)
        ).fetchone()
        if batch["status"] == "sealed" or (period and period["status"] == "sealed"):
            raise HTTPException(409, "批已用于封印，不能再作废")
        if batch["status"] == "expired":
            return {
                "batch_id": batch_id,
                "status": "expired",
                "already": True,
                "message": "批已作废，无需重复操作",
            }
        now = _now()
        conn.execute(
            """UPDATE reconcile_batches
                  SET status='expired', invalidated_at=?, invalidated_reason=?
                WHERE batch_id=? AND status='open'""",
            (now, f"{actor}:{reason}", batch_id),
        )
        return {
            "batch_id": batch_id,
            "status": "expired",
            "already": False,
            "invalidated_at": now,
            "message": "批已作废，须重跑对齐才能封印",
        }


# ---------------------------------------------------------------- 对齐

def run_align(period_id: str) -> dict:
    with write_tx() as conn:
        assert_period_writable_conn(conn, period_id)
        est = {
            r["meter_id"]: r
            for r in conn.execute(
                "SELECT * FROM estimates WHERE period_id=? ORDER BY loaded_at, estimate_id",
                (period_id,),
            ).fetchall()
        }
        act = {
            r["meter_id"]: r
            for r in conn.execute(
                "SELECT * FROM actuals WHERE period_id=? ORDER BY loaded_at, actual_id",
                (period_id,),
            ).fetchall()
        }
        keys = sorted(set(est) | set(act))
        if not keys:
            raise HTTPException(400, "该账期无估抄/实抄可对齐")

        # 重跑对齐本身即取代旧 open 批（两架构一致：显式对齐不是隐式失效）
        conn.execute(
            "UPDATE reconcile_batches SET status='expired', invalidated_at=?, invalidated_reason='realign' "
            "WHERE period_id=? AND status='open'",
            (_now(), period_id),
        )

        batch_id = "B-" + uuid.uuid4().hex[:10]
        matched = 0
        variances = []
        content: list[str] = []
        for mid in keys:
            eq = est[mid]["qty"] if mid in est else None
            aq = act[mid]["qty"] if mid in act else None
            content.append(f"{mid}:{eq!r}:{aq!r}")
            if eq is not None and aq is not None and abs(eq - aq) < 1e-9:
                matched += 1
                continue
            delta = (aq if aq is not None else 0.0) - (eq if eq is not None else 0.0)
            variances.append(
                (
                    "V-" + uuid.uuid4().hex[:10],
                    batch_id,
                    mid,
                    period_id,
                    eq,
                    aq,
                    delta,
                    "pending",
                )
            )

        watermark = period_load_watermark(conn, period_id) or _now()
        source_sig = source_signature(conn, period_id)
        # 指纹覆盖对齐后的真实内容 + 本次依据的全部装载行：
        # 数量变化、或同表号多装一条，都必须换指纹，不能沿用旧指纹
        fp_src = (
            f"{period_id}|{matched}|{len(variances)}|" + ",".join(content) + f"|{source_sig}"
        )
        fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()[:16]
        conn.execute(
            """INSERT INTO reconcile_batches(
                   batch_id,period_id,status,matched_count,variance_count,fingerprint,
                   created_at,source_loaded_at,source_sig)
               VALUES (?,?,'open',?,?,?,?,?,?)""",
            (
                batch_id,
                period_id,
                matched,
                len(variances),
                fingerprint,
                _now(),
                watermark,
                source_sig,
            ),
        )
        if variances:
            conn.executemany(
                """INSERT INTO variances(variance_id,batch_id,meter_id,period_id,estimate_qty,actual_qty,delta,fate)
                   VALUES (?,?,?,?,?,?,?,?)""",
                variances,
            )
        return {
            "batch_id": batch_id,
            "period_id": period_id,
            "matched_count": matched,
            "variance_count": len(variances),
            "fingerprint": fingerprint,
            "status": "open",
            "source_loaded_at": watermark,
            "is_stale": False,
        }


# ---------------------------------------------------------------- 封印

def seal_period(
    period_id: str, batch_id: str | None = None, acknowledge_stale: bool = False
) -> dict:
    with write_tx() as conn:
        mode = read_invalidation_mode(conn)
        period = conn.execute(
            "SELECT * FROM periods WHERE period_id=?", (period_id,)
        ).fetchone()
        if not period:
            raise HTTPException(404, "账期不存在")
        if period["status"] == "sealed":
            raise HTTPException(409, "账期已封印")

        if batch_id:
            batch = conn.execute(
                "SELECT * FROM reconcile_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if not batch or batch["period_id"] != period_id:
                raise HTTPException(400, "对账批与账期不匹配")
        else:
            batch = conn.execute(
                """SELECT * FROM reconcile_batches WHERE period_id=? AND status='open'
                   ORDER BY created_at DESC LIMIT 1""",
                (period_id,),
            ).fetchone()
            if not batch:
                raise HTTPException(400, "无 open 对账批，请先对齐")

        if batch["status"] == "expired":
            raise HTTPException(409, "对账批已作废，不得用于封印；请重跑对齐")
        if batch["status"] == "sealed":
            raise HTTPException(409, "对账批已封印，不得重复引用")
        if batch["status"] != "open":
            raise HTTPException(409, "对账批不可用")
        if not batch["fingerprint"]:
            raise HTTPException(409, "对账批缺少指纹，请重跑对齐")

        # 陈旧判定在写事务内完成：并发装载要么先失效此批，要么被此封印挡在后面
        watermark = period_load_watermark(conn, period_id)
        signature = source_signature(conn, period_id)
        stale = _is_stale(batch, watermark, signature)
        stale_acknowledged = False
        if stale:
            if mode == "auto":
                raise HTTPException(
                    409, "对账批已陈旧（装载后未重跑对齐），请重跑对齐后再封印"
                )
            if not acknowledge_stale:
                raise HTTPException(
                    409,
                    "对账批可能陈旧：装载成功后未重跑对齐。请重跑对齐，或显式确认按旧指纹封印",
                )
            stale_acknowledged = True

        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM variances WHERE batch_id=? AND fate='pending'",
            (batch["batch_id"],),
        ).fetchone()["c"]
        sealed_at = _now()
        conn.execute(
            "UPDATE periods SET status='sealed', sealed_at=?, batch_no=? WHERE period_id=?",
            (sealed_at, batch["batch_id"], period_id),
        )
        conn.execute(
            "UPDATE reconcile_batches SET status='sealed' WHERE batch_id=?",
            (batch["batch_id"],),
        )
        return {
            "period_id": period_id,
            "batch_id": batch["batch_id"],
            "fingerprint": batch["fingerprint"],
            "invalidation_mode": mode,
            "stale_acknowledged": stale_acknowledged,
            "sealed_at": sealed_at,
            "pending_left": pending,
            "status": "sealed",
        }


# ---------------------------------------------------------------- 差额

def set_fate(variance_id: str, fate: str) -> dict:
    if fate not in ("pending", "accept_short", "accept_over", "quarantine"):
        raise HTTPException(400, "非法命运")
    with write_tx() as conn:
        row = conn.execute(
            """SELECT v.*, p.status AS period_status, b.status AS batch_status
                 FROM variances v
                 JOIN periods p ON p.period_id=v.period_id
                 JOIN reconcile_batches b ON b.batch_id=v.batch_id
                WHERE v.variance_id=?""",
            (variance_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "差额不存在")
        if row["period_status"] == "sealed":
            raise HTTPException(409, "账期已封印，禁止改命运")
        if row["batch_status"] == "expired":
            raise HTTPException(409, "差额所属批已作废，请在对齐后的新批处置")
        conn.execute("UPDATE variances SET fate=? WHERE variance_id=?", (fate, variance_id))
        return {"variance_id": variance_id, "fate": fate}
