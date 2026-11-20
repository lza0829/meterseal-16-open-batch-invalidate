<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { 批可用, 批可用色, 批状态, 失效架构, 账期状态, 标 } from '../labels'

const router = useRouter()
const data = ref(null)
const err = ref('')
const msg = ref('')

async function load() {
  err.value = ''
  try { data.value = await api.overview() } catch (e) { err.value = e.message }
}

async function invalidate(batchId) {
  err.value = ''; msg.value = ''
  try {
    const r = await api.invalidateBatch(batchId, 'overview-manual')
    msg.value = r.message || '已作废'
    await load()
  } catch (e) { err.value = e.message }
}

function goSeal(periodId) {
  router.push({ path: '/seal', query: { period: periodId } })
}
function goAlign(periodId) {
  router.push({ path: '/reconcile', query: { period: periodId } })
}

onMounted(load)
</script>
<template>
  <div>
    <h1>总览</h1>
    <p class="sub">当前账期估抄、实抄、对齐与封印状态</p>
    <p v-if="err" class="msg err">{{ err }}</p>
    <p v-if="msg" class="msg ok">{{ msg }}</p>

    <div class="grid" v-if="data">
      <div class="stat">当前账期<b>{{ data.current_period }}</b></div>
      <div class="stat">开放账期<b>{{ data.open_periods }}</b></div>
      <div class="stat">已封印账期<b>{{ data.sealed_periods }}</b></div>
      <div class="stat">表具数<b>{{ data.meter_count }}</b></div>
      <div class="stat">未决差额<b>{{ data.pending_variances }}</b></div>
      <div class="stat" :class="{ alarm: data.stale_open_batches > 0 }">
        陈旧开放批<b>{{ data.stale_open_batches }}</b>
      </div>
    </div>

    <div class="panel" v-if="data">
      <h3>账期与对账批</h3>
      <p class="hint">失效架构：{{ 标(失效架构, data.batch_invalidation) }}</p>
      <table>
        <thead>
          <tr>
            <th>账期</th><th>账期状态</th><th>开放批</th><th>陈旧批</th>
            <th>最近批</th><th>最近批可用性</th><th>封印口径</th><th>入口</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in data.periods" :key="p.period_id">
            <td>{{ p.period_id }}</td>
            <td><span class="tag" :class="p.status">{{ 标(账期状态, p.status) }}</span></td>
            <td>{{ p.open_batch_count }}</td>
            <td :class="{ danger: p.stale_batch_count > 0 }">{{ p.stale_batch_count }}</td>
            <td>{{ p.latest_batch ? p.latest_batch.batch_id : '—' }}</td>
            <td>
              <span v-if="p.latest_batch" class="tag" :class="批可用色[p.latest_batch.usability]">
                {{ 标(批可用, p.latest_batch.usability) }}
              </span>
              <span v-else>—</span>
            </td>
            <td class="hint">{{ p.seal_hint || '—' }}</td>
            <td>
              <button class="secondary" @click="goAlign(p.period_id)">重跑对齐</button>
              <button
                v-if="p.stale_batch_ids.length && data.batch_invalidation === 'manual'"
                class="warn" @click="invalidate(p.stale_batch_ids[0])"
              >失效陈旧批</button>
              <button v-else-if="p.status !== 'sealed'" class="secondary" @click="goSeal(p.period_id)">
                去封印
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel" v-if="data">
      <h3>最近对账批</h3>
      <table>
        <thead><tr><th>批号</th><th>账期</th><th>匹配</th><th>差额</th><th>状态</th><th>可用性</th><th>提示</th></tr></thead>
        <tbody>
          <tr v-for="b in data.recent_batches" :key="b.batch_id">
            <td>{{ b.batch_id }}</td>
            <td>{{ b.period_id }}</td>
            <td>{{ b.matched_count }}</td>
            <td>{{ b.variance_count }}</td>
            <td><span class="tag" :class="b.status">{{ 标(批状态, b.status) }}</span></td>
            <td><span class="tag" :class="批可用色[b.usability]">{{ 标(批可用, b.usability) }}</span></td>
            <td class="hint">{{ b.stale_hint || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
