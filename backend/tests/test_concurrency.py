"""并发：装载/人工失效 与 封印同时打到同一批，不得出现半截结果。"""
from __future__ import annotations
import itertools
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient

_counter = itertools.count()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "race.db"
    os.environ["METERCALC_DB_PATH"] = str(db)
    from app.main import app

    with TestClient(app) as c:
        yield c


def new_period(client) -> str:
    """并发线程各建连接，提前把账期写进库。"""
    from app.db import connect

    pid = f"RACE-{next(_counter)}-{os.getpid()}"
    conn = connect()
    try:
        conn.execute("INSERT OR IGNORE INTO periods(period_id,status) VALUES (?,'open')", (pid,))
        conn.commit()
    finally:
        conn.close()
    return pid


def _prepare(client, pid, mode):
    client.put("/api/settings/batch_invalidation", json={"value": mode})
    client.post(
        "/api/estimates",
        json={"meter_id": "M-W-101", "period_id": pid, "qty": 10, "doc_no": f"{pid}-E"},
    )
    r = client.post("/api/align", json={"period_id": pid})
    assert r.status_code == 200, r.text
    return r.json()["batch_id"]


def _race(fns):
    out = {}

    def wrap(key, fn):
        out[key] = fn()

    threads = [threading.Thread(target=wrap, args=(k, f)) for k, f in fns.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def _load(client, pid):
    return client.post(
        "/api/actuals",
        json={
            "meter_id": "M-W-101",
            "period_id": pid,
            "qty": 11,
            "occurred_at": "2026-10-29T09:00:00",
            "reader_code": "R",
            "doc_no": f"{pid}-A",
        },
    )


def test_auto_load_vs_seal_never_half_applies(client):
    for _ in range(5):
        pid = new_period(client)
        bid = _prepare(client, pid, "auto")
        out = _race(
            {
                "load": lambda: _load(client, pid),
                "seal": lambda: client.post("/api/seal", json={"period_id": pid, "batch_id": bid}),
            }
        )
        load_ok = out["load"].status_code == 200
        seal_ok = out["seal"].status_code == 200
        # 自动架构：装载先 -> 批已 expired，封印必须 409；封印先 -> 装载 409
        assert load_ok != seal_ok, (pid, out["load"].text, out["seal"].text)


def test_manual_load_vs_seal_requires_explicit_stale_ack(client):
    for _ in range(5):
        pid = new_period(client)
        bid = _prepare(client, pid, "manual")
        # 未确认陈旧：装载若先成功，封印必须被陈旧校验挡下
        out = _race(
            {
                "load": lambda: _load(client, pid),
                "seal": lambda: client.post("/api/seal", json={"period_id": pid, "batch_id": bid}),
            }
        )
        load_ok = out["load"].status_code == 200
        seal_ok = out["seal"].status_code == 200
        if load_ok and seal_ok:
            raise AssertionError(
                f"manual 架构未确认陈旧却封印成功: {pid} {out['seal'].text}"
            )
        assert not seal_ok or not load_ok

    # 显式确认后：装载先成功则封印允许，但必须回报 stale_acknowledged
    for _ in range(5):
        pid = new_period(client)
        bid = _prepare(client, pid, "manual")
        out = _race(
            {
                "load": lambda: _load(client, pid),
                "seal": lambda: client.post(
                    "/api/seal",
                    json={"period_id": pid, "batch_id": bid, "acknowledge_stale": True},
                ),
            }
        )
        load_ok = out["load"].status_code == 200
        seal_ok = out["seal"].status_code == 200
        # 唯一不允许的组合是「两者都成功却没标记已确认陈旧」
        if load_ok and seal_ok:
            assert out["seal"].json()["stale_acknowledged"] is True
        else:
            assert load_ok or seal_ok


def test_manual_invalidate_vs_seal(client):
    for _ in range(5):
        pid = new_period(client)
        bid = _prepare(client, pid, "manual")
        out = _race(
            {
                "inv": lambda: client.post(f"/api/batches/{bid}/invalidate", json={"reason": "race"}),
                "seal": lambda: client.post("/api/seal", json={"period_id": pid, "batch_id": bid}),
            }
        )
        codes = {out["inv"].status_code, out["seal"].status_code}
        assert codes == {200, 409}, (pid, out["inv"].text, out["seal"].text)
