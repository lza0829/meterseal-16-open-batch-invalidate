<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { 批可用, 批可用色, 批状态, 标 } from '../labels'

const router = useRouter()
const periodId = ref('2026-10')
const rows = ref([])
const batches = ref([])
const form = ref({ meter_id: 'M-W-101', period_id: '2026-10', qty: 10, doc_no: '' })
const msg = ref('')
const err = ref('')
const hook = ref(null)

async function load() {
  err.value = ''
  rows.value = await api.estimates(periodId.value)
  batches.value = await api.batches(periodId.value)
}

async function submit() {
  err.value = ''; msg.value = ''; hook.value = null
  try {
    const body = { ...form.value, doc_no: form.value.doc_no || ('估-' + Date.now()) }
    const r = await api.postEstimate(body)
    hook.value = r
    msg.value = r.notice || '估抄已装载'
    await load()
  } catch (e) { err.value = e.message }
}

function goAlign() {
  router.push({ path: '/reconcile', query: { period: form.value.period_id } })
}

watch(periodId, () => { load().catch(e => { err.value = e.message }) })
onMounted(() => { load().catch(e => { err.value = e.message }) })
</script>
<template>
  <div>
    <h1>估抄</h1>
    <p class="sub">按账期装载估抄读数</p>
    <div class="row">
      <label>账期筛选<input v-model="periodId" /></label>
      <button class="secondary" @click="load">刷新</button>
    </div>
    <div class="panel">
      <div class="row">
        <label>表号<input v-model="form.meter_id" /></label>
        <label>账期<input v-model="form.period_id" /></label>
        <label>数量<input type="number" step="0.1" v-model.number="form.qty" /></label>
        <label>单号<input v-model="form.doc_no" placeholder="可空自动生成" /></label>
        <button @click="submit">装载估抄</button>
      </div>
      <p class="msg ok" v-if="msg">{{ msg }}</p>
      <p class="msg err" v-if="err">{{ err }}</p>
      <p v-if="hook && hook.needs_realign" class="msg err">
        旧对账批已不能直接封印，请
        <button class="secondary" @click="goAlign">重跑对齐</button>
      </p>
      <table>
        <thead><tr><th>编号</th><th>表号</th><th>账期</th><th>数量</th><th>单号</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.estimate_id">
            <td>{{ r.estimate_id }}</td>
            <td>{{ r.meter_id }}</td>
            <td>{{ r.period_id }}</td>
            <td>{{ r.qty }}</td>
            <td>{{ r.doc_no }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel" v-if="batches.length">
      <h3>该账期对账批</h3>
      <table>
        <thead><tr><th>批号</th><th>状态</th><th>可用性</th><th>提示</th></tr></thead>
        <tbody>
          <tr v-for="b in batches" :key="b.batch_id">
            <td>{{ b.batch_id }}</td>
            <td><span class="tag" :class="b.status">{{ 标(批状态, b.status) }}</span></td>
            <td><span class="tag" :class="批可用色[b.usability]">{{ 标(批可用, b.usability) }}</span></td>
            <td class="hint">{{ b.stale_hint || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
