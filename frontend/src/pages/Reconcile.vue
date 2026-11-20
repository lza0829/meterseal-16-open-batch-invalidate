<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { 批可用, 批可用色, 批状态, 命运, 失效架构, 标 } from '../labels'

const route = useRoute()
const periodId = ref(route.query.period || '2026-10')
const batch = ref(null)
const vars = ref([])
const msg = ref('')
const err = ref('')

function pickDisplay(batches) {
  // 优先展示开放批，否则展示最近一批（含已作废旧批，便于对照）
  return batches.find(b => b.status === 'open') || batches[0] || null
}

async function refresh() {
  err.value = ''
  const bs = await api.batches(periodId.value)
  batch.value = pickDisplay(bs)
  vars.value = batch.value ? await api.variances({ batch_id: batch.value.batch_id }) : []
}

async function align() {
  err.value = ''; msg.value = ''
  try {
    const fresh = await api.align(periodId.value)
    batch.value = fresh
    vars.value = await api.variances({ batch_id: fresh.batch_id })
    msg.value = `对齐完成：匹配 ${fresh.matched_count}，差额 ${fresh.variance_count}`
  } catch (e) { err.value = e.message }
}

async function fate(id, f) {
  err.value = ''
  try {
    await api.setFate(id, f)
    vars.value = await api.variances({ batch_id: batch.value.batch_id })
  } catch (e) { err.value = e.message }
}

async function invalidate() {
  if (!batch.value) return
  err.value = ''; msg.value = ''
  try {
    const r = await api.invalidateBatch(batch.value.batch_id, 'reconcile-manual')
    msg.value = r.message || '批已作废'
    await refresh()
  } catch (e) { err.value = e.message }
}

watch(periodId, () => { refresh().catch(e => { err.value = e.message }) })
onMounted(() => { refresh().catch(e => { err.value = e.message }) })
</script>
<template>
  <div>
    <h1>对齐差额</h1>
    <p class="sub">按表号与账期对齐估抄、实抄；装载后旧批会按失效架构处理</p>
    <div class="row">
      <label>账期<input v-model="periodId" /></label>
      <button @click="align">重跑对齐</button>
      <button class="secondary" @click="refresh">刷新</button>
    </div>
    <p class="msg ok" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>

    <div class="panel" v-if="batch">
      <p>
        批号 {{ batch.batch_id }} · 指纹 {{ batch.fingerprint }} ·
        <span class="tag" :class="batch.status">{{ 标(批状态, batch.status) }}</span>
        <span class="tag" :class="批可用色[batch.usability]">{{ 标(批可用, batch.usability) }}</span>
      </p>
      <p v-if="batch.stale_hint" class="msg err">
        {{ batch.stale_hint }}（当前架构：{{ 标(失效架构, batch.invalidation_mode) }}）
        <button v-if="batch.status === 'open'" class="warn" @click="invalidate">人工失效此批</button>
      </p>
      <p v-if="batch.status !== 'open'" class="hint">
        此批不可再封印；请按「重跑对齐」生成新批后再到封印页操作。
      </p>
      <table>
        <thead><tr><th>差额编号</th><th>表号</th><th>估抄</th><th>实抄</th><th>差值</th><th>命运</th><th>处置</th></tr></thead>
        <tbody>
          <tr v-for="v in vars" :key="v.variance_id">
            <td>{{ v.variance_id }}</td>
            <td>{{ v.meter_id }}</td>
            <td>{{ v.estimate_qty }}</td>
            <td>{{ v.actual_qty }}</td>
            <td>{{ v.delta }}</td>
            <td>{{ 标(命运, v.fate) }}</td>
            <td>
              <button class="secondary" :disabled="batch.status !== 'open'"
                      @click="fate(v.variance_id, 'accept_short')">认短</button>
              <button class="secondary" :disabled="batch.status !== 'open'"
                      @click="fate(v.variance_id, 'accept_over')">认溢</button>
              <button class="warn" :disabled="batch.status !== 'open'"
                      @click="fate(v.variance_id, 'quarantine')">隔离</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!vars.length" class="hint">此批无差额。</p>
    </div>
    <p v-else class="hint">该账期还没有对账批，先重跑对齐。</p>
  </div>
</template>
