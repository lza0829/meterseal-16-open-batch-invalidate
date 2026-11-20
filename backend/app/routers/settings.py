from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db import connect
from app.services.gate import INVALIDATION_MODES, read_invalidation_mode

router = APIRouter(tags=["settings"])


class SettingIn(BaseModel):
    value: str


@router.get("/settings")
def list_settings():
    conn = connect()
    try:
        data = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings").fetchall()}
        # 失效架构总以生效值出现，避免设置页看不到默认值
        data["batch_invalidation"] = read_invalidation_mode(conn)
        return data
    finally:
        conn.close()


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn):
    if key == "batch_invalidation" and body.value not in INVALIDATION_MODES:
        raise HTTPException(400, "失效架构只能是 auto（自动作废）或 manual（人工失效）")
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, body.value),
        )
        conn.commit()
        return {"key": key, "value": body.value}
    finally:
        conn.close()
