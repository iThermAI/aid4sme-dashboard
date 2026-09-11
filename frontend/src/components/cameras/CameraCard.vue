<script setup>
import { computed, ref } from 'vue'
import { store } from '../../store.js'
import { api } from '../../api.js'
import { t, camName, checkText, errorText } from '../../i18n.js'
import { timeOfDay } from '../../format.js'

const props = defineProps({
  id: { type: String, required: true },
  info: { type: Object, default: null },
  loading: Boolean,
  error: { type: String, default: '' }
})
const emit = defineEmits(['refresh'])

const ip = computed(() => (props.info && props.info.ip) || (store.config.cameras.find((c) => c.id === props.id) || {}).ip)
const streams = computed(() => (props.info && props.info.streams) || [])
const byKind = computed(() => Object.fromEntries(streams.value.map((s) => [s.kind, s])))
const checks = computed(() => (props.info && props.info.checks) || [])
const order = { warn: 0, unknown: 1, ok: 2 }
const sortedChecks = computed(() => checks.value.slice().sort((a, b) => order[a.status] - order[b.status]))
const warnCount = computed(() => checks.value.filter((c) => c.status === 'warn').length)
const thermal = computed(() => (props.info && props.info.thermal) || [])
const reference = computed(() => props.info && props.info.reference)
const showAll = ref(false)
const showOk = ref(false)

// ---- rename the channel shown on the video ------------------------------------
const editing = ref('')
const newName = ref('')
const renameMsg = ref('')
const renameOk = ref(true)
function startEdit (kind) {
  editing.value = kind
  newName.value = (byKind.value[kind] && byKind.value[kind].name) || ''
  renameMsg.value = ''
}
async function saveName () {
  try {
    const r = await api.renameChannel(props.id, editing.value, newName.value)
    renameOk.value = r.ok
    renameMsg.value = r.ok ? t('cameras.renameSaved') : t('cameras.renameFailed')
    editing.value = ''
    emit('refresh')
  } catch (e) {
    renameOk.value = false
    renameMsg.value = errorText(e)
  }
}

// ---- shutter calibration (only if configured) ------------------------------------
const ffcMsg = ref('')
async function ffc () {
  try {
    const r = await api.ffc(props.id)
    ffcMsg.value = r.ok ? t('cameras.ffcDone') : (r.message || 'HTTP ' + r.http)
  } catch (e) { ffcMsg.value = errorText(e) }
}

function streamVal (kind, attr) {
  const s = byKind.value[kind]
  if (!s || !s.available) return '\u2013'
  switch (attr) {
    case 'codec': return s.codec || '\u2013'
    case 'resolution': return s.width ? `${s.width} × ${s.height}` : '\u2013'
    case 'fps': return s.fps !== null ? t('cameras.frames', { v: s.fps }) : '\u2013'
    case 'bitrate': return `${s.bitrate_type || ''}${s.bitrate_kbps ? ' ' + s.bitrate_kbps + ' kbit/s' : ''}` || '\u2013'
    case 'gop': return s.gop !== null ? t('cameras.gopFrames', { v: s.gop }) : '\u2013'
  }
  return '\u2013'
}
function streamWarn (kind, attr) {
  const map = { resolution: 'resolution', fps: 'fps', gop: 'gop', bitrate: 'bitrate_type', codec: 'codec' }
  return checks.value.some((c) => c.stream === kind && c.id === map[attr] && c.status === 'warn')
}
function thermalWarn (key) {
  const map = { palette: 'palette', agc: 'agc', range: 'range', measurement_overlay: 'measurement_overlay',
    distance: 'distance_vs_reference', emissivity: 'emissivity_vs_reference', level_span: 'level_span',
    noise_reduction: 'noise_reduction', digital_zoom: 'digital_zoom', p2p_refresh: 'p2p_refresh' }
  if (key === 'p2p_emissivity' || key === 'p2p_distance') {
    return checks.value.some((c) => c.id === 'p2p_mismatch' && c.status === 'warn' && 'p2p_' + c.field === key)
  }
  return checks.value.some((c) => c.id === map[key] && c.status === 'warn')
}
function thermalValue (f) {
  if (f.value === null || f.value === undefined) return null
  const v = f.unit ? `${f.value} ${f.unit}` : f.value
  return f.detail ? `${v} (${f.detail})` : v
}
const sectionLabel = (s) => `${s.name} ${s.path ? '(' + s.path + ')' : ''}`
</script>

<template>
  <article class="card panel">
    <header class="chead">
      <div class="ttl">
        <span class="dot" :class="info ? (info.reachable ? '' : 'fault') : 'idle'"></span>
        <h2>{{ camName(id) }}</h2>
        <span class="muted num">{{ ip }}</span>
        <span v-if="info && info.identity" class="muted small">{{ info.identity.model }}</span>
      </div>
      <div class="acts">
        <span v-if="info && info.read_at" class="xs muted">{{ t('cameras.refreshed', { t: timeOfDay(info.read_at) }) }}</span>
        <a class="btn sm" :href="'http://' + ip" target="_blank" rel="noopener">{{ t('cameras.openWeb') }}</a>
        <button class="btn sm" :disabled="loading" @click="emit('refresh')">{{ loading ? t('common.loading') : t('common.refresh') }}</button>
      </div>
    </header>

    <p v-if="error" class="notice fault m">{{ error }}</p>
    <p v-else-if="info && !info.reachable" class="notice fault m">{{ t('setup.offline') }}: {{ info.error }}</p>
    <p v-else-if="!info" class="m muted">{{ t('common.loading') }}</p>

    <template v-if="info && info.reachable">
      <!-- Names on the video -->
      <section class="sec">
        <h3>{{ t('cameras.nameOnVideo') }}</h3>
        <div v-for="kind in ['optical', 'thermal']" :key="kind" class="namerow">
          <span class="kind">{{ t('stream.' + kind) }}</span>
          <template v-if="editing === kind">
            <input v-model="newName" maxlength="32" :aria-label="t('cameras.nameOnVideo')" @keydown.enter="saveName" @keydown.esc="editing = ''" />
            <button class="btn sm primary" @click="saveName">{{ t('common.save') }}</button>
            <button class="btn sm ghost" @click="editing = ''">{{ t('common.cancel') }}</button>
          </template>
          <template v-else>
            <span class="osd">{{ (byKind[kind] && byKind[kind].name) || '\u2013' }}</span>
            <span v-if="byKind[kind] && byKind[kind].overlay.channel_name !== null" class="xs muted">
              {{ byKind[kind].overlay.channel_name ? t('cameras.nameShown') : t('cameras.nameHidden') }}
            </span>
            <button class="link small" :disabled="!!store.status && store.status.state !== 'idle' && store.status.state !== 'finished'" @click="startEdit(kind)">{{ t('cameras.rename') }}</button>
          </template>
        </div>
        <p v-if="renameMsg" class="small" :class="renameOk ? 'oktext' : 'err'">{{ renameMsg }}</p>
      </section>

      <!-- Settings check -->
      <section class="sec">
        <div class="shead">
          <h3>{{ t('cameras.checks') }}</h3>
          <span v-if="warnCount" class="badge warn">{{ warnCount }}</span>
          <span v-else class="badge ok">{{ t('setup.settingsOk') }}</span>
          <span v-if="reference" class="xs muted refline">
            {{ reference.changes.length ? t('profiles.changesVsRef', { n: reference.changes.length, p: reference.name }) : t('profiles.matchesRef', { p: reference.name }) }}
          </span>
        </div>
        <ul class="checks">
          <li v-for="(c, i) in sortedChecks" v-show="showOk || c.status !== 'ok'" :key="i" :class="c.status">
            <span class="ic" aria-hidden="true">{{ c.status === 'ok' ? '\u2713' : c.status === 'warn' ? '!' : '?' }}</span>
            <span><template v-if="c.stream">{{ t('stream.' + c.stream) }}: </template>{{ checkText(c) }}</span>
          </li>
          <li v-if="reference && reference.changes.length" class="warn">
            <span class="ic">!</span>
            <span>{{ t('profiles.changesVsRef', { n: reference.changes.length, p: reference.name }) }}:
              <span v-for="(ch, i) in reference.changes.slice(0, 6)" :key="i" class="chg num">{{ ch.key.split('/').pop() }} {{ ch.old }} → {{ ch.new }}</span>
            </span>
          </li>
        </ul>
        <button class="link xs" @click="showOk = !showOk">{{ showOk ? '−' : '+' }} {{ checks.filter((c) => c.status === 'ok').length }} OK</button>
      </section>

      <!-- Thermal image and measurement -->
      <section class="sec">
        <h3>{{ t('cameras.thermal') }}</h3>
        <table class="kv">
          <tr v-for="f in thermal" :key="f.key" :class="{ key: f.key === 'distance', w: thermalWarn(f.key) }">
            <th>{{ t('cameras.attr.' + f.key) }}</th>
            <td>
              <span v-if="thermalValue(f) !== null" class="val num">{{ thermalValue(f) }}</span>
              <span v-else class="xs muted">{{ t('cameras.unknownField') }}</span>
              <p v-if="f.key === 'distance'" class="xs hint">{{ t('cameras.distanceHint') }}</p>
            </td>
            <td class="src xs muted">{{ f.source ? f.source.split(': ')[0] : '' }}</td>
          </tr>
        </table>
        <div v-if="store.config.ffc_available" class="ffc">
          <button class="btn sm" @click="ffc">{{ t('cameras.ffc') }}</button>
          <span v-if="ffcMsg" class="small muted">{{ ffcMsg }}</span>
        </div>
      </section>

      <!-- Streams -->
      <section class="sec">
        <h3>{{ t('cameras.streams') }}</h3>
        <table class="kv streams">
          <tr><th></th><th class="colh">{{ t('stream.optical') }}</th><th class="colh">{{ t('stream.thermal') }}</th></tr>
          <tr v-for="a in ['codec', 'resolution', 'fps', 'bitrate', 'gop']" :key="a">
            <th>{{ t('cameras.attr.' + a) }}</th>
            <td v-for="k in ['optical', 'thermal']" :key="k" class="num" :class="{ w: streamWarn(k, a) }">{{ streamVal(k, a) }}</td>
          </tr>
        </table>
      </section>

      <!-- Device and time -->
      <section class="sec">
        <h3>{{ t('cameras.device') }}</h3>
        <table class="kv">
          <tr><th>{{ t('cameras.model') }}</th><td>{{ info.identity.model || '\u2013' }}</td></tr>
          <tr><th>{{ t('cameras.serial') }}</th><td class="num">{{ info.identity.serialNumber || '\u2013' }}</td></tr>
          <tr><th>{{ t('cameras.firmware') }}</th><td class="num">{{ info.identity.firmwareVersion }} {{ info.identity.firmwareReleasedDate }}</td></tr>
          <tr><th>{{ t('cameras.mac') }}</th><td class="num">{{ info.identity.macAddress || '\u2013' }}</td></tr>
          <tr><th>{{ t('cameras.timeMode') }}</th><td>{{ info.time.mode || '\u2013' }}</td></tr>
          <tr><th>{{ t('cameras.ntpServer') }}</th><td class="num">{{ info.time.ntp_server || '\u2013' }}</td></tr>
          <tr><th>{{ t('cameras.clock') }}</th><td class="num">{{ info.time.drift_s !== null && info.time.drift_s !== undefined ? info.time.drift_s + ' s' : '\u2013' }}</td></tr>
        </table>
      </section>

      <!-- Everything read -->
      <section class="sec">
        <button class="link small" :aria-expanded="showAll" @click="showAll = !showAll">{{ showAll ? '−' : '+' }} {{ t('cameras.allValues') }}</button>
        <div v-if="showAll" class="raw">
          <div v-for="s in info.sections" :key="s.name" class="rawsec">
            <p class="xs strong num">{{ sectionLabel(s) }}
              <span v-if="s.status !== 200" class="muted">: {{ t('cameras.notAvailable') }} (HTTP {{ s.status }})</span></p>
            <table v-if="s.values.length" class="kv mini">
              <tr v-for="[k, v] in s.values" :key="k"><th class="num">{{ k }}</th><td class="num">{{ v }}</td></tr>
            </table>
          </div>
        </div>
      </section>
    </template>
  </article>
</template>

<style scoped>
.card { display: flex; flex-direction: column; min-width: 0; }
.chead { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.ttl { display: flex; align-items: center; gap: 10px; }
.ttl h2 { font-size: var(--fs-lg); }
.acts { display: flex; align-items: center; gap: 8px; }
a.btn { text-decoration: none; }
.m { margin: 14px 16px; }
.sec { padding: 12px 16px; border-bottom: 1px solid var(--line); }
.sec:last-child { border-bottom: 0; }
.sec h3 { margin-bottom: 8px; font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; }
.shead { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.shead h3 { margin: 0; }
.refline { margin-left: auto; }
.namerow { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.namerow input { max-width: 220px; min-height: 30px; }
.kind { width: 80px; color: var(--muted); font-size: var(--fs-sm); }
.osd {
  font-family: var(--font-read);
  font-size: 16px;
  font-weight: 500;
  padding: 1px 10px;
  border-radius: 4px;
  background: var(--video-bg);
  color: #fff;
}
.checks { list-style: none; margin: 0 0 4px; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-sm); }
.checks li { display: flex; gap: 8px; align-items: baseline; }
.ic { width: 16px; height: 16px; border-radius: 50%; display: inline-grid; place-items: center; font-size: 10px; font-weight: 700; flex: 0 0 auto; transform: translateY(2px); }
.checks .ok .ic { background: var(--ok-soft); color: var(--ok); }
.checks .warn { color: var(--warn-ink); font-weight: 500; }
.checks .warn .ic { background: var(--warn); color: #fff; }
.checks .unknown { color: var(--muted); }
.checks .unknown .ic { background: var(--surface-3); color: var(--muted); }
.chg { display: inline-block; margin: 0 6px; padding: 0 6px; border-radius: 3px; background: var(--warn-soft); }
table.kv { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.kv th { text-align: left; font-weight: 500; color: var(--muted); padding: 4px 12px 4px 0; width: 42%; vertical-align: top; }
.kv td { padding: 4px 8px 4px 0; vertical-align: top; }
.kv tr + tr th, .kv tr + tr td { border-top: 1px solid var(--line); }
.kv tr.key { background: var(--primary-soft); }
.kv tr.key th { color: var(--primary); font-weight: 600; padding-left: 6px; }
.kv tr.key .val { font-weight: 700; font-size: var(--fs-md); }
.kv tr.w td .val, .kv td.w { color: var(--warn-ink); font-weight: 600; }
.kv .src { text-align: right; width: 1%; white-space: nowrap; }
.hint { color: var(--ink-2); margin-top: 2px; max-width: 48ch; }
.streams th.colh { color: var(--ink-2); text-transform: capitalize; width: auto; }
.streams th:first-child { width: 34%; }
.ffc { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.raw { margin-top: 8px; max-height: 360px; overflow-y: auto; }
.rawsec + .rawsec { margin-top: 10px; }
.strong { font-weight: 600; }
.mini th { width: 60%; font-weight: 400; word-break: break-all; }
.mini td { word-break: break-all; }
.oktext { color: var(--ok); margin-top: 4px; }
.err { color: var(--fault); margin-top: 4px; }
</style>
