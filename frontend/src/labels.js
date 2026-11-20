/** 界面文案映射：库内码 → 中文（页面不直接露英文码） */
export const 表类型 = { water: '水表', electric: '电表', 水表: '水表', 电表: '电表' }
export const 表状态 = { active: '在用', inactive: '停用', 在用: '在用', 停用: '停用' }
export const 账期状态 = { open: '开放', sealed: '已封印', expired: '已作废', 开放: '开放', 已封印: '已封印' }
export const 批状态 = { open: '开放', sealed: '已封印', expired: '已作废' }
export const 命运 = {
  pending: '未决',
  accept_short: '认短',
  accept_over: '认溢',
  quarantine: '隔离',
}

/** 批的可用口径：usable 可直接封；stale 陈旧（人工架构需确认）；expired 已作废 */
export const 批可用 = {
  usable: '可封印',
  stale: '陈旧·可能沿用旧指纹',
  expired: '已作废·须重跑对齐',
  sealed: '已封印',
}
export const 批可用色 = { usable: 'usable', stale: 'stale', expired: 'expired', sealed: 'sealed' }

export const 失效架构 = {
  auto: '自动作废（装载即失效开放批）',
  manual: '人工失效（装载仅提示陈旧）',
}

export function 标(map, key) {
  if (key == null || key === '') return '—'
  return map[key] || String(key)
}
