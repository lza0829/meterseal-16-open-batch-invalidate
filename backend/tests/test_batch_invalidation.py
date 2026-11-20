"""装载钩子 / 批状态 / 封印校验 / 失效入口 / 对齐 / 总览的联动测试。

每个用例用独立 SQLite 文件，经 TestClient 走真实 HTTP 路由。
"""
from __future__ import annotations
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def _app_client(tmp_path_factory):
    # import 之前就要定好库路径：app.main 顶层会 seed
    db = tmp_path_factory.mktemp("db") / "t.db"
    os.environ["METERCALC_DB_PATH"] = str(db)
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(_app_client):
    # 每个用例一份新库：删文件后重新种子，连接是每请求新建的，无需重启应用
    from app import config
    from app.seed import seed_if_empty

    config.DB_PATH.unlink(missing_ok=True)
    seed_if_empty()
    return _app_client


def post_actual(c, meter="M-W-101", period="2026-10", qty=12.0, doc=None):
    return c.post(
        "/api/actuals",
        json={
            "meter_id": meter,
            "period_id": period,
            "qty": qty,
            "occurred_at": "2026-10-29T09:00:00",
            "reader_code": "R09",
            "doc_no": doc or f"T-{abs(hash((meter, period, qty, doc)))}",
        },
    )


def align(c, period="2026-10"):
    r = c.post("/api/align", json={"period_id": period})
    assert r.status_code == 200, r.text
    return r.json()


def set_mode(c, mode):
    r = c.put("/api/settings/batch_invalidation", json={"value": mode})
    assert r.status_code == 200, r.text


def latest_open(c, period="2026-10"):
    bs = c.get("/api/batches", params={"period_id": period}).json()
    return next((b for b in bs if b["status"] == "open"), None)


# ------------------------------------------------------------ 自动架构

def test_auto_load_expires_open_batch_and_blocks_seal(client):
    b = align(client)
    assert latest_open(client)["batch_id"] == b["batch_id"]

    r = post_actual(client)
    assert r.status_code == 200, r.text
    hook = r.json()
    assert hook["invalidation_mode"] == "auto"
    assert b["batch_id"] in hook["invalidated_batches"]
    assert hook["needs_realign"] is True
    assert "作废" in hook["notice"]

    assert latest_open(client) is None
    sealed = client.post(
        "/api/seal", json={"period_id": "2026-10", "batch_id": b["batch_id"]}
    )
    assert sealed.status_code == 409
    assert "作废" in sealed.json()["detail"]

    # 自动架构下即使显式确认陈旧也不能封
    forced = client.post(
        "/api/seal",
        json={
            "period_id": "2026-10",
            "batch_id": b["batch_id"],
            "acknowledge_stale": True,
        },
    )
    assert forced.status_code == 409


def test_auto_realign_after_load_allows_seal(client):
    b1 = align(client)
    post_actual(client)
    b2 = align(client)
    assert b2["batch_id"] != b1["batch_id"]
    assert b2["fingerprint"] != b1["fingerprint"]

    ok = client.post("/api/seal", json={"period_id": "2026-10", "batch_id": b2["batch_id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "sealed"


def test_estimate_load_also_invalidates(client):
    b = align(client)
    r = client.post(
        "/api/estimates",
        json={"meter_id": "M-W-102", "period_id": "2026-10", "qty": 99.0, "doc_no": "EST-T1"},
    )
    assert r.status_code == 200, r.text
    assert b["batch_id"] in r.json()["invalidated_batches"]
    assert latest_open(client) is None


# ------------------------------------------------------------ 人工架构

def test_manual_mode_keeps_batch_open_but_flags_stale(client):
    set_mode(client, "manual")
    b = align(client)

    r = post_actual(client)
    assert r.status_code == 200, r.text
    hook = r.json()
    assert hook["invalidation_mode"] == "manual"
    assert hook["invalidated_batches"] == []
    assert b["batch_id"] in hook["stale_batches"]
    assert hook["needs_realign"] is True

    still_open = latest_open(client)
    assert still_open["batch_id"] == b["batch_id"]
    assert still_open["is_stale"] is True

    detail = client.get(f"/api/batches/{b['batch_id']}").json()
    assert detail["is_stale"] is True
    assert detail["usability"] == "stale"
    assert "陈旧" in detail["stale_hint"]

    # 未显式确认：拒绝，但有陈旧提示，不是静默成功
    blocked = client.post("/api/seal", json={"period_id": "2026-10", "batch_id": b["batch_id"]})
    assert blocked.status_code == 409
    assert "陈旧" in blocked.json()["detail"]

    # 显式确认后可按旧指纹封印（人工架构口径）
    acked = client.post(
        "/api/seal",
        json={"period_id": "2026-10", "batch_id": b["batch_id"], "acknowledge_stale": True},
    )
    assert acked.status_code == 200, acked.text
    assert acked.json()["stale_acknowledged"] is True


def test_manual_stale_batch_flagged_in_overview(client):
    set_mode(client, "manual")
    align(client)
    post_actual(client)
    ov = client.get("/api/overview").json()
    assert ov["batch_invalidation"] == "manual"
    assert ov["stale_open_batches"] >= 1
    p = next(p for p in ov["periods"] if p["period_id"] == "2026-10")
    assert p["stale_batch_count"] >= 1
    assert "陈旧" in p["seal_hint"]


# ------------------------------------------------------------ 人工失效入口（两架构共用）

@pytest.mark.parametrize("mode", ["auto", "manual"])
def test_manual_invalidation_blocks_seal_in_both_modes(client, mode):
    set_mode(client, mode)
    b = align(client)
    inv = client.post(f"/api/batches/{b['batch_id']}/invalidate", json={"reason": "test"})
    assert inv.status_code == 200, inv.text
    assert inv.json()["status"] == "expired"

    r = client.post(
        "/api/seal",
        json={"period_id": "2026-10", "batch_id": b["batch_id"], "acknowledge_stale": True},
    )
    assert r.status_code == 409

    # 作废后不得再改差额命运
    vs = client.get("/api/variances", params={"batch_id": b["batch_id"]}).json()
    if vs:
        fr = client.post(
            f"/api/variances/{vs[0]['variance_id']}/fate", json={"fate": "accept_short"}
        )
        assert fr.status_code == 409


def test_already_sealed_batch_cannot_be_invalidated(client):
    b = align(client)
    client.post("/api/seal", json={"period_id": "2026-10", "batch_id": b["batch_id"]})
    inv = client.post(f"/api/batches/{b['batch_id']}/invalidate", json={})
    assert inv.status_code == 409


# ------------------------------------------------------------ 指纹与陈旧判定

def test_fingerprint_changes_with_quantity(client):
    b1 = align(client)
    post_actual(client, meter="M-W-101", qty=12.0, doc="DUP-Q")
    b2 = align(client)
    post_actual(client, meter="M-W-101", qty=13.0, doc="DUP-Q2")
    b3 = align(client)
    assert len({b1["fingerprint"], b2["fingerprint"], b3["fingerprint"]}) == 3


def test_align_refuses_sealed_period(client):
    b = align(client)
    client.post("/api/seal", json={"period_id": "2026-10", "batch_id": b["batch_id"]})
    r = client.post("/api/align", json={"period_id": "2026-10"})
    assert r.status_code == 409


def test_seal_without_batch_picks_none_when_only_expired(client):
    align(client)
    post_actual(client)
    r = client.post("/api/seal", json={"period_id": "2026-10"})
    assert r.status_code == 400
    assert "对齐" in r.json()["detail"]


def test_new_load_after_seal_is_rejected(client):
    b = align(client)
    client.post("/api/seal", json={"period_id": "2026-10", "batch_id": b["batch_id"]})
    r = post_actual(client)
    assert r.status_code == 409
    assert "封印" in r.json()["detail"]
