// 前端行为自检入口：真正挂载页面组件（客户端模式），由 tests/ui-check.mjs 驱动
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Home from '../src/pages/Home.vue'
import Reconcile from '../src/pages/Reconcile.vue'
import Seal from '../src/pages/Seal.vue'
import Actuals from '../src/pages/Actuals.vue'
import Estimates from '../src/pages/Estimates.vue'
import Settings from '../src/pages/Settings.vue'

const PAGES = { Home, Reconcile, Seal, Actuals, Estimates, Settings }

export function batch(over = {}) {
  return {
    batch_id: 'B-DEMO', period_id: '2026-10', status: 'open', matched_count: 4, variance_count: 2,
    fingerprint: 'abc123', created_at: '2026-11-20T10:00:00+00:00',
    source_loaded_at: '2026-11-20T09:00:00+00:00',
    invalidation_mode: 'manual', is_stale: true, usability: 'stale',
    stale_hint: '批已陈旧：装载成功后未重跑对齐，指纹可能不再代表现数据',
    load_watermark: '2026-11-20T11:00:00+00:00', period_status: 'open', ...over,
  }
}

export async function mountPage(name, path, query = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path, component: PAGES[name] }] })
  router.push({ path, query })
  await router.isReady()
  const w = mount(PAGES[name], { global: { plugins: [router] } })
  await new Promise((r) => setTimeout(r, 80))
  await w.vm.$nextTick()
  return w
}
