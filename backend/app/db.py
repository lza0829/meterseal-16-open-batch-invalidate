from __future__ import annotations
import sqlite3
from app import config


def connect() -> sqlite3.Connection:
    data_dir = config.DB_PATH.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    # 写事务用 BEGIN IMMEDIATE 串行化；timeout 让并发装载/封印等待而不是直接报锁
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn
