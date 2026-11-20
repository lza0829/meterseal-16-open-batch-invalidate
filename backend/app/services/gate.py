from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from app.db import connect

INVALIDATION_MODES = ("auto", "manual")
DEFAULT_INVALIDATION_MODE = "auto"
INVALIDATION_MODE_KEY = "batch_invalidation"


@contextmanager
def write_tx() -> Iterator[sqlite3.Connection]:
    """写事务：BEGIN IMMEDIATE 先拿写锁，装载钩子与封印校验互斥。

    装载与封印都不允许「读到旧数据后再写入」的半截事务；SQLite 的
    RESERVED 锁会把两者串行化，后到者要么看到已作废的批，要么看到已封印的账期。
    """
    conn = connect()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def read_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def read_invalidation_mode(conn: sqlite3.Connection) -> str:
    mode = read_setting(conn, INVALIDATION_MODE_KEY, DEFAULT_INVALIDATION_MODE)
    return mode if mode in INVALIDATION_MODES else DEFAULT_INVALIDATION_MODE


def get_invalidation_mode() -> str:
    conn = connect()
    try:
        return read_invalidation_mode(conn)
    finally:
        conn.close()


def assert_period_writable_conn(conn: sqlite3.Connection, period_id: str) -> None:
    row = conn.execute(
        "SELECT status FROM periods WHERE period_id=?", (period_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"账期不存在: {period_id}")
    if row["status"] == "sealed":
        raise HTTPException(409, f"账期已封印，禁止写入: {period_id}")


def assert_period_writable(period_id: str) -> None:
    conn = connect()
    try:
        assert_period_writable_conn(conn, period_id)
    finally:
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = connect()
    try:
        return read_setting(conn, key, default)
    finally:
        conn.close()
