<script setup>
import { computed } from 'vue'
import { t, streamLabel } from '../../i18n.js'
import { num, signedMs } from '../../format.js'

const props = defineProps({ result: { type: Object, required: true } })

const offsetsKey = computed(() => Object.keys(props.result).find((k) => k.startsWith('start_offsets_ms_vs_')))
const reference = computed(() => (offsetsKey.value ? offsetsKey.value.replace('start_offsets_ms_vs_', '') : ''))
const offsets = computed(() => (offsetsKey.value ? props.result[offsetsKey.value] : {}))

function videoDetail (v) {
  const p = []
  if (v.start_delay_s > 0.5) p.push(t('verify.late', { v: num(v.start_delay_s, 1) }))
  if (v.ratio_vs_span < 0.999) p.push(t('verify.missing', { v: num((1 - v.ratio_vs_span) * 100, 1) }))
  if (v.stop && v.stop !== 'graceful') p.push(v.stop)
  if (v.stalled_during_run) p.push(t('verify.interrupted'))
  if (v.ffmpeg_warnings) p.push(t('verify.ffmpegWarn', { n: v.ffmpeg_warnings }))
  return p.join(', ')
}
function radDetail (r) {
  const p = []
  if (r.capture_uncertainty_ms && r.capture_uncertainty_ms.median !== undefined) p.push(t('verify.timing', { v: num(r.capture_uncertainty_ms.median, 0) }))
  if (r.tmax_c !== undefined && r.tmax_c !== null) p.push(t('rec.maxT', { v: num(r.tmax_c, 1) }))
  if (r.freeze_frames) p.push(t('rec.freezes', { n: r.freeze_frames }))
  if (r.saturated_frames) p.push(t('rec.ceiling', { n: r.saturated_frames }))
  if (r.failed) p.push(t('rec.failed', { n: r.failed }))
  return p.join(', ')
}
</script>

<template>
  <table class="data">
    <thead>
      <tr>
        <th>{{ t('verify.stream') }}</th><th>{{ t('verify.result') }}</th><th class="r">{{ t('verify.recorded') }}</th>
        <th class="r">{{ t('verify.offset') }}<span v-if="reference" class="muted"> ({{ streamLabel(reference) }})</span></th>
        <th>{{ t('verify.notes') }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="v in result.video || []" :key="v.stream" :class="{ bad: !v.pass }">
        <td class="name">{{ streamLabel(v.stream) }}</td>
        <td><span class="st"><span class="dot" :class="v.pass ? '' : 'fault'"></span>{{ v.pass ? t('verify.complete') : t('verify.problem') }}</span></td>
        <td class="r num">{{ t('verify.framesIn', { n: v.packets, s: num(v.span_s, 0) }) }}</td>
        <td class="r num">{{ offsets[v.stream] !== undefined ? signedMs(offsets[v.stream]) : '\u2013' }}</td>
        <td class="small">{{ videoDetail(v) }}</td>
      </tr>
      <tr v-for="r in result.radiometric || []" :key="r.stream" :class="{ bad: !r.pass }">
        <td class="name">{{ streamLabel(r.stream) }}</td>
        <td><span class="st"><span class="dot" :class="r.pass ? '' : 'fault'"></span>{{ r.pass ? t('verify.complete') : t('verify.problem') }}</span></td>
        <td class="r num">{{ t('verify.matrices', { n: r.unique_matrices || 0, r: num(r.unique_fps, 2) }) }}</td>
        <td class="r num">&ndash;</td>
        <td class="small">{{ radDetail(r) }}</td>
      </tr>
    </tbody>
  </table>
  <p v-if="result.start_offsets_note" class="xs muted note">{{ t('verify.offsetNote') }}</p>
</template>

<style scoped>
.name { font-weight: 500; white-space: nowrap; }
.st { display: inline-flex; align-items: center; gap: 8px; }
.note { margin: 8px 12px 10px; max-width: 90ch; }
</style>
