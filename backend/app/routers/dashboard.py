from __future__ import annotations
from fastapi import APIRouter
from app.db import connect
from app.services import reconcile_service
from app.services.gate import get_setting

router = APIRouter(tags=["dashboard"])


@router.get("/health")
def health():
    return {"ok": True, "product": "抄表簿"}


@router.get("/overview")
def overview():
    conn = connect()
    try:
        open_periods = conn.execute(
            "SELECT COUNT(*) AS c FROM periods WHERE status='open'"
        ).fetchone()["c"]
        sealed_periods = conn.execute(
            "SELECT COUNT(*) AS c FROM periods WHERE status='sealed'"
        ).fetchone()["c"]
        meters = conn.execute("SELECT COUNT(*) AS c FROM meters").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM variances WHERE fate='pending'"
        ).fetchone()["c"]
        current = get_setting("current_period", "")
        mode = reconcile_service.read_invalidation_mode(conn)

        # 总览与批详情同口径：陈旧批必须在这里也露出来，不能只在详情页提示
        periods = []
        for p in conn.execute("SELECT * FROM periods ORDER BY period_id DESC").fetchall():
            pid = p["period_id"]
            watermark = reconcile_service.period_load_watermark(conn, pid)
            signature = reconcile_service.source_signature(conn, pid)
            rows = conn.execute(
                "SELECT * FROM reconcile_batches WHERE period_id=? ORDER BY created_at DESC",
                (pid,),
            ).fetchall()
            batches = [
                reconcile_service.decorate_batch(r, watermark, mode, signature) for r in rows
            ]
            open_batches = [b for b in batches if b["status"] == "open"]
            stale = [b for b in open_batches if b["is_stale"]]
            periods.append(
                {
                    "period_id": pid,
                    "status": p["status"],
                    "batch_no": p["batch_no"],
                    "sealed_at": p["sealed_at"],
                    "open_batch_count": len(open_batches),
                    "stale_batch_count": len(stale),
                    "stale_batch_ids": [b["batch_id"] for b in stale],
                    "seal_blocked": p["status"] != "sealed" and not open_batches,
                    "seal_hint": (
                        "须重跑对齐后才能封印"
                        if p["status"] != "sealed" and not open_batches
                        else ("存在陈旧开放批，请重跑对齐或人工失效" if stale else "")
                    ),
                    "latest_batch": batches[0] if batches else None,
                }
            )

        return {
            "current_period": current,
            "open_periods": open_periods,
            "sealed_periods": sealed_periods,
            "meter_count": meters,
            "pending_variances": pending,
            "batch_invalidation": mode,
            "stale_open_batches": sum(p["stale_batch_count"] for p in periods),
            "periods": periods,
            "recent_batches": sorted(
                (b for p in periods for b in ([p["latest_batch"]] if p["latest_batch"] else [])),
                key=lambda b: b["created_at"],
                reverse=True,
            )[:8],
        }
    finally:
        conn.close()
