<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { 批可用, 批可用色, 批状态, 失效架构, 账期状态, 标 } from '../labels'

const route = useRoute()
const router = useRouter()
const periods = ref([])
const periodId = ref(route.query.period || '2026-10')
const batchId = ref('')
const detail = ref(null)
const acknowledgeStale = ref(false)
const mode = ref('auto')
const msg = ref('')
const err = ref('')

const sealable = computed(() => {
  if (!detail.value) return false
  if (detail.value.period_status === 'sealed') return false
  if (detail.value.usability === 'usable') return true
  // 人工架构允许显式确认陈旧后按旧指纹封印；自动架构一律拒绝
  return mode.value === 'manual' && detail.value.usability === 'stale' && acknowledgeStale.value
})

async function loadDetail() {
  detail.value = null
  if (!batchId.value) return
  try {
    detail.value = await api.batchDetail(batchId.value)
    mode.value = detail.value.invalidation_mode || mode.value
  } catch (e) { err.value = e.message }
}

async function refresh() {
  err.value = ''
  const s = await api.settings()
  mode.value = s.batch_invalidation || 'auto'
  periods.value = await api.periods()
  const bs = await api.batches(periodId.value)
  if (!bs.find(b => b.batch_id === batchId.value)) {
    const chosen = bs.find(b => b.status === 'open') || bs[0]
    batchId.value = chosen ? chosen.batch_id : ''
  }
  await loadDetail()
}

async function seal() {
  err.value = ''; msg.value = ''
  try {
    const r = await api.seal({
      period_id: periodId.value,
      batch_id: batchId.value || null,
      acknowledge_stale: acknowledgeStale.value,
    })
    msg.value = `已封印 ${r.period_id}，绑定批 ${r.batch_id}，指纹 ${r.fingerprint}` +
      (r.stale_acknowledged ? '（已确认按陈旧指纹封印）' : '')
    acknowledgeStale.value = false
    await refresh()
  } catch (e) { err.value = e.message }
}

async function invalidate() {
  if (!batchId.value) return
  err.value = ''; msg.value = ''
  try {
    const r = await api.invalidateBatch(batchId.value, 'seal-page')
    msg.value = r.message || '批已作废'
    await refresh()
  } catch (e) { err.value = e.message }
}

function goAlign() {
  router.push({ path: '/reconcile', query: { period: periodId.value } })
}

watch(periodId, () => { refresh().catch(e => { err.value = e.message }) })
watch(batchId, () => {
  acknowledgeStale.value = false
  loadDetail().catch(e => { err.value = e.message })
})
onMounted(() => { refresh().catch(e => { err.value = e.message }) })
</script>
<template>
  <div>
    <h1>账期封印</h1>
    <p class="sub">封印后该期估抄、实抄禁止再写；封印绑定的批必须可用</p>
    <div class="row">
      <label>账期<input v-model="periodId" /></label>
      <label>对账批<input v-model="batchId" placeholder="可空取最新开放批" /></label>
      <button class="warn" :disabled="!detail || !sealable" @click="seal">封印账期</button>
      <button class="secondary" @click="refresh">刷新</button>
      <button class="secondary" @click="goAlign">重跑对齐</button>
      <button
        v-if="detail && detail.status === 'open'"
        class="warn" @click="invalidate"
      >人工失效此批</button>
    </div>
    <p class="msg ok" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>

    <div class="panel" v-if="detail">
      <p>
        批 {{ detail.batch_id }} · 指纹 {{ detail.fingerprint }} ·
        <span class="tag" :class="detail.status">{{ 标(批状态, detail.status) }}</span>
        <span class="tag" :class="批可用色[detail.usability]">{{ 标(批可用, detail.usability) }}</span>
      </p>
      <p class="hint">
        当前失效架构：{{ 标(失效架构, detail.invalidation_mode) }} ·
        批依据装载时刻 {{ detail.source_loaded_at || '—' }} ·
        账期最新装载时刻 {{ detail.load_watermark || '—' }}
      </p>
      <p v-if="detail.stale_hint" class="msg err">{{ detail.stale_hint }}</p>
      <p v-if="detail.status === 'expired'" class="msg err">
        此批已作废，封印会被拒绝；请点「重跑对齐」生成新批。
      </p>
      <label v-if="detail.usability === 'stale' && detail.invalidation_mode === 'manual'" class="check">
        <input type="checkbox" v-model="acknowledgeStale" />
        我已知晓该批按旧数据对齐，仍按旧指纹封印？
      </label>
      <p v-if="detail.period_status === 'sealed'" class="hint">该账期已封印。</p>
    </div>
    <p v-else class="hint">该账期暂无对账批，请先重跑对齐。</p>

    <div class="panel">
      <h3>账期一览</h3>
      <table>
        <thead><tr><th>账期</th><th>状态</th><th>封印时刻</th><th>绑定批</th></tr></thead>
        <tbody>
          <tr v-for="p in periods" :key="p.period_id">
            <td>{{ p.period_id }}</td>
            <td><span class="tag" :class="p.status">{{ 标(账期状态, p.status) }}</span></td>
            <td>{{ p.sealed_at || '—' }}</td>
            <td>{{ p.batch_no || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
