<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { 失效架构, 标 } from '../labels'

const current = ref('')
const mode = ref('auto')
const msg = ref('')
const err = ref('')

async function load() {
  const s = await api.settings()
  current.value = s.current_period || ''
  mode.value = s.batch_invalidation || 'auto'
}

async function save() {
  err.value = ''; msg.value = ''
  try {
    await api.putSetting('current_period', current.value)
    msg.value = '已保存当前账期'
    await load()
  } catch (e) { err.value = e.message }
}

async function saveMode() {
  err.value = ''; msg.value = ''
  try {
    await api.putSetting('batch_invalidation', mode.value)
    msg.value = `已切换失效架构：${标(失效架构, mode.value)}`
    await load()
  } catch (e) { err.value = e.message }
}

onMounted(load)
</script>
<template>
  <div>
    <h1>设置</h1>
    <p class="sub">运行参数</p>
    <div class="panel">
      <div class="row">
        <label>当前账期<input v-model="current" /></label>
        <button @click="save">保存</button>
      </div>
      <p class="msg ok" v-if="msg">{{ msg }}</p>
      <p class="msg err" v-if="err">{{ err }}</p>
    </div>

    <div class="panel">
      <h3>批失效架构</h3>
      <p class="hint">
        切换后即时生效，只影响此后发生的装载与封印判断；既有批状态不改写。
        两种架构都不得在无任何陈旧提示的情况下沿用旧指纹封印。
      </p>
      <div class="row">
        <label>架构
          <select v-model="mode">
            <option value="auto">自动作废（装载即失效开放批）</option>
            <option value="manual">人工失效（装载仅提示陈旧，需人工点失效）</option>
          </select>
        </label>
        <button @click="saveMode">保存架构</button>
      </div>
      <p class="hint">
        自动架构：新装载后旧开放批 status=expired，封印直接拒绝，须重跑对齐。<br />
        人工架构：新装载不改批态，批详情与总览标「陈旧」，封印需显式确认或人工失效。
      </p>
    </div>
  </div>
</template>
