// 前端联动行为自检：真挂载页面组件，断言「陈旧提示 / 封印门槛 / 失效入口 / 重跑对齐」。
// 用 `npm run test:ui` 运行：会先打客户端包，再执行本文件。
import { JSDOM } from 'jsdom'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://127.0.0.1:6010/' })
const win = dom.window
const GLOBALS = [
  'window', 'document', 'history', 'location', 'MutationObserver', 'Event', 'CustomEvent',
  'KeyboardEvent', 'MouseEvent', 'DOMRect', 'getComputedStyle', 'Text', 'Comment',
  'DocumentFragment', 'requestAnimationFrame', 'cancelAnimationFrame', 'XMLSerializer',
  'Document', 'ShadowRoot', 'Node', 'Element', 'HTMLElement', 'SVGElement',
  'HTMLInputElement', 'HTMLSelectElement', 'HTMLButtonElement', 'HTMLAnchorElement',
  'HTMLDivElement', 'HTMLSpanElement', 'HTMLParagraphElement', 'HTMLLabelElement',
  'HTMLTableElement', 'HTMLTableRowElement', 'HTMLTableCellElement', 'HTMLTableSectionElement',
]
for (const k of GLOBALS) globalThis[k] = win[k]
Object.defineProperty(globalThis, 'navigator', { value: win.navigator, configurable: true })

const state = { detail: null, batches: [], variances: [], mode: 'manual', overview: {} }
let overrides = {}
const json = (body) => ({
  ok: true, status: 200,
  text: async () => JSON.stringify(body),
  json: async () => body,
})

globalThis.fetch = async (url, opts = {}) => {
  const u = String(url)
  for (const [needle, fn] of Object.entries(overrides)) if (u.includes(needle)) return json(fn(u, opts))
  if (/\/api\/batches\/[^/?]+$/.test(u)) return json(state.detail)
  if (u.includes('/api/batches')) return json(state.batches)
  if (u.includes('/api/variances')) return json(state.variances)
  if (u.includes('/api/settings')) return json({ batch_invalidation: state.mode, current_period: '2026-10' })
  if (u.includes('/api/periods')) return json([{ period_id: '2026-10', status: 'open' }])
  if (u.includes('/api/overview')) return json(state.overview)
  return json({})
}

const { batch, mountPage } = await import(path.join(root, 'tests/.ui-dist/bundle.mjs'))

let fails = 0
const check = (name, cond, extra = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' :: ' + extra : ''}`)
  if (!cond) fails++
}
const text = (c) => c.text().replace(/\s+/g, ' ')
const byLabel = (c, label) => c.findAll('button').find((b) => b.text() === label)
const disabled = (b) => !b || b.attributes('disabled') !== undefined

// ---- 封印页：人工架构 + 陈旧批
state.mode = 'manual'
state.detail = batch()
state.batches = [batch()]
let w = await mountPage('Seal', '/seal', { period: '2026-10' })
check('封印页露出陈旧提示', text(w).includes('批已陈旧'))
check('封印页露出当前架构', text(w).includes('人工失效'))
check('人工架构陈旧批：未确认时封印按钮禁用', disabled(byLabel(w, '封印账期')))
check('存在确认陈旧勾选框', w.find('input[type="checkbox"]').exists())
await w.find('input[type="checkbox"]').setValue(true)
await w.vm.$nextTick()
check('勾选确认后可封印', !disabled(byLabel(w, '封印账期')))
check('存在人工失效此批按钮', w.findAll('button').some((b) => b.text() === '人工失效此批'))

// ---- 封印页：自动架构 + 陈旧批（拒绝且无确认口）
state.mode = 'auto'
state.detail = batch({ invalidation_mode: 'auto' })
w = await mountPage('Seal', '/seal', { period: '2026-10' })
check(
  '自动架构陈旧批：按钮禁用且无确认口',
  disabled(byLabel(w, '封印账期')) && !w.find('input[type="checkbox"]').exists()
)

// ---- 封印页：已作废批
state.detail = batch({
  status: 'expired', usability: 'expired', is_stale: false, invalidation_mode: 'auto',
  stale_hint: '批已作废，须重跑对齐后才能封印',
})
w = await mountPage('Seal', '/seal', { period: '2026-10' })
check('作废批给出重跑对齐提示', text(w).includes('此批已作废'))
check('作废批封印按钮禁用', disabled(byLabel(w, '封印账期')))

// ---- 对齐页：作废批不可改命运
state.batches = [batch({ status: 'expired', usability: 'expired', is_stale: false })]
state.variances = [{ variance_id: 'V1', meter_id: 'M-W-101', estimate_qty: 12, actual_qty: 14, delta: 2, fate: 'pending' }]
state.detail = state.batches[0]
w = await mountPage('Reconcile', '/reconcile', { period: '2026-10' })
check(
  '对齐页对作废批禁用处置',
  w.findAll('button').filter((b) => ['认短', '认溢', '隔离'].includes(b.text())).every(disabled)
)
check('对齐页显示作废批状态', text(w).includes('已作废'))

// ---- 总览：陈旧开放批醒目 + 两入口同口径
state.overview = {
  current_period: '2026-10', open_periods: 2, sealed_periods: 1, meter_count: 6, pending_variances: 2,
  batch_invalidation: 'manual', stale_open_batches: 1,
  periods: [{
    period_id: '2026-10', status: 'open', open_batch_count: 1, stale_batch_count: 1,
    stale_batch_ids: ['B-DEMO'], latest_batch: batch(), seal_hint: '存在陈旧开放批，请重跑对齐或人工失效',
  }],
  recent_batches: [batch()],
}
w = await mountPage('Home', '/', {})
check('总览显示陈旧开放批数', /陈旧开放批\s*1/.test(w.text()))
check('总览露出陈旧提示', text(w).includes('陈旧'))
check('总览有人工失效入口', w.findAll('button').some((b) => b.text() === '失效陈旧批'))
check('总览有重跑对齐入口', w.findAll('button').some((b) => b.text() === '重跑对齐'))

// ---- 装载页：装载返回 needs_realign 时必须提示，不得静默
for (const [page, route, label] of [['Actuals', '/actuals', '实抄'], ['Estimates', '/estimates', '估抄']]) {
  state.batches = [batch({ status: 'expired', usability: 'expired', is_stale: false })]
  overrides = {
    [`/api${route}`]: () => ({
      ok: true, invalidation_mode: 'auto', invalidated_batches: ['B-DEMO'], needs_realign: true,
      notice: '已装载；1 个开放批自动作废，须重跑对齐后再封印',
    }),
  }
  w = await mountPage(page, route, {})
  await w.findAll('button').find((b) => b.text().includes('装载')).trigger('click')
  await new Promise((r) => setTimeout(r, 80))
  await w.vm.$nextTick()
  check(`${label}页装载后提示重跑对齐`, text(w).includes('重跑对齐'))
  check(`${label}页列出对账批可用性`, text(w).includes('已作废'))
  overrides = {}
}

// ---- 设置页：两架构可切换
state.mode = 'auto'
w = await mountPage('Settings', '/settings', {})
check('设置页有架构选择', w.findAll('option').length === 2)
check('设置页说明不得静默沿用旧指纹', text(w).includes('旧指纹'))

console.log(`\n${fails === 0 ? 'ALL PASS' : fails + ' FAILURES'}`)
process.exit(fails ? 1 : 0)
