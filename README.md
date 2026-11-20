# 抄表簿

估抄/实抄装载 → 对齐差额 → 账期封印。骨架之上补齐「新装载后 open 批如何失效」的联动口径。

- 前端 http://127.0.0.1:6010（勿用 6000，浏览器会拦）
- 接口 http://127.0.0.1:11000

## 批失效架构（设置页可切换，默认 `auto`）

| 场景 | `auto`（自动作废） | `manual`（人工失效） |
|---|---|---|
| 装载估抄/实抄后旧 open 批 | 立即 `expired` | 保持 `open`，标「陈旧」 |
| 封印该旧批 | 409，须重跑对齐 | 409；勾选确认后可按旧指纹封印 |
| 人工失效入口 | 有 | 有 |
| 失效后封印 | 拒绝 | 拒绝 |
| 总览 / 批详情 | 显示作废与重跑入口 | 显示陈旧提示与失效入口 |

两种架构都禁止「装载成功后仍无任何提示地沿用旧指纹封印」，且装载与封印在写事务内串行，
不会拿到半截作废的批。详见 `backend/README.md`。

## 启动

```bash
cd backend
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 11000 --app-dir .
```

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 6010
```

## 自检

```bash
cd backend && python -m pytest tests -q     # 含并发用例
cd frontend && npm run test:ui              # 真挂载页面的联动断言
```
