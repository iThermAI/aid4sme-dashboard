<script setup>
import { computed } from 'vue'
import { t, streamLabel } from '../../i18n.js'
import { mb, num } from '../../format.js'

const props = defineProps({ s: { type: Object, required: true }, nominal: { type: Number, default: 25 } })

const DOT = { ok: '', starting: 'idle', stalled: 'fault', dead: 'fault', stopping: 'idle', stopped: 'idle', off: 'idle' }
const bad = computed(() => props.s.health === 'dead' || props.s.health === 'stalled')

const rate = computed(() => {
  const s = props.s
  if (s.type === 'video') return `${num(s.fps, 1)} fps`
  if (s.type === 'radiometric') return `${num(s.fps, 2)} /s`
  if (s.type === 'keyence' && s.records !== undefined) return String(s.records)
  return '\u2013'
})
const lastData = computed(() => {
  const s = props.s
  const v = s.type === 'video' ? s.since_growth_s : s.type === 'radiometric' ? s.since_ok_s : s.since_record_s
  return v === null || v === undefined ? '\u2013' : `${num(v, 0)} s`
})
const details = computed(() => {
  const s = props.s
  if (s.type === 'video') return t('rec.frames', { n: s.frames, m: num(s.mbps, 1) })
  if (s.type === 'radiometric') {
    const p = []
    if (s.tmax !== null && s.tmax !== undefined) p.push(t('rec.maxT', { v: num(s.tmax, 1) }))
    if (s.rtt_ms !== null && s.rtt_ms !== undefined) p.push(t('rec.response', { v: num(s.rtt_ms, 0) }))
    if (s.freeze) p.push(t('rec.freezes', { n: s.freeze }))
    if (s.failed) p.push(t('rec.failed', { n: s.failed }))
    if (s.saturated) p.push(t('rec.ceiling', { n: s.saturated }))
    return p.join(', ')
  }
  return s.note || ''
})

// Frame-rate trace for the last minute; a dip below the dashed nominal line is a dropout.
const W = 120
const H = 24
const spark = computed(() => {
  const h = props.s.fps_history || []
  if (h.length < 2) return null
  const top = props.nominal * 1.25
  const pts = h.map((v, i) => `${(i / (h.length - 1)) * W},${H - Math.min(v / top, 1) * H}`).join(' ')
  return { pts, nominalY: H - (props.nominal / top) * H }
})
</script>

<template>
  <tr :class="{ bad }">
    <td class="name">{{ streamLabel(s.name) }}</td>
    <td>
      <span class="st"><span class="dot" :class="DOT[s.health] === undefined ? 'idle' : DOT[s.health]"></span>{{ t('rec.health.' + s.health) }}</span>
      <span v-if="s.freeze_active" class="muted small"> ({{ t('rec.shutter') }})</span>
    </td>
    <td class="r num">{{ rate }}</td>
    <td class="r num">{{ s.mb !== undefined ? mb(s.mb) : '\u2013' }}</td>
    <td class="r num">{{ lastData }}</td>
    <td>
      <svg v-if="spark" :viewBox="`0 0 ${W} ${H}`" :width="W" :height="H" class="spark" aria-hidden="true">
        <line x1="0" :y1="spark.nominalY" :x2="W" :y2="spark.nominalY" class="nominal" />
        <polyline :points="spark.pts" class="trace" />
      </svg>
    </td>
    <td class="small num muted">{{ details }}</td>
  </tr>
</template>

<style scoped>
.name { font-weight: 500; white-space: nowrap; }
.st { display: inline-flex; align-items: center; gap: 8px; }
tr.bad .st { color: var(--fault-ink); font-weight: 600; }
.spark { display: block; overflow: visible; }
.nominal { stroke: var(--line-strong); stroke-dasharray: 3 3; }
.trace { fill: none; stroke: var(--primary); stroke-width: 1.5; }
tr.bad .trace { stroke: var(--fault); }
</style>
