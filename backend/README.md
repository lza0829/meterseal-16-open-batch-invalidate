# 抄表簿 · 后端

## 批失效架构（两选一，全局只贯彻一种，设置页可切换）

| | auto（默认） | manual |
|---|---|---|
| 新装载后 open 批 | status=`expired`，`invalidated_reason='new_load'` | 不改批态，标 `is_stale` |
| 封印旧 open 批 | 直接 409，须重跑对齐 | 409；显式 `acknowledge_stale=true` 才可按旧指纹封印 |
| 批详情/总览提示 | 「已作废，须重跑对齐」 | 「可能陈旧」+ 人工失效按钮 |
| 失效入口 | `POST /api/batches/{id}/invalidate`（两架构通用） | 同左 |

两架构共同约束：

- 装载写入与失效钩子在同一 `BEGIN IMMEDIATE` 事务内，封印校验也在写事务内判定陈旧，
  不存在「装载成功却仍静默沿用旧指纹」或「半截用已该失效的指纹」。
- 封印只接受 `status='open'` 且指纹存在、且不陈旧的批；`expired`/`sealed` 一律拒绝。
- 重跑对齐会作废该账期旧 open 批并生成新批；指纹覆盖对齐内容与全部装载行。
- 批/总览的 `usability ∈ {usable, stale, expired, sealed}` 是唯一口径，页面按它渲染。

## 接口补充

- `GET /api/batches?period_id=` 每项含 `usability / is_stale / stale_hint / source_loaded_at`。
- `GET /api/batches/{id}` 批详情，含 `load_watermark / period_status / can_seal`。
- `POST /api/batches/{id}/invalidate` 人工失效（已封印/已用其封印的批拒绝）。
- `POST /api/seal` 可选 `acknowledge_stale`，仅 manual 架构生效，返回 `stale_acknowledged`。
- `POST /api/estimates|actuals` 返回装载钩子结果：`invalidated_batches / stale_batches / needs_realign / notice`。
- `PUT /api/settings/batch_invalidation` 取值 `auto|manual`。

## 测试

```bash
pip install -r requirements.txt pytest httpx
python -m pytest tests -q
```

`tests/test_batch_invalidation.py` 覆盖两架构的装载→失效→封印链路、人工失效、指纹变化、
已封印保护；并含并发用例（见 `tests/test_concurrency.py`）。
