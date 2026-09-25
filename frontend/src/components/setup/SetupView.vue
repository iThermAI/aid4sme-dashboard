<script setup>
import { computed, ref } from 'vue'
import { store } from '../../store.js'
import { api } from '../../api.js'
import { t, blockerText, warningText, errorText } from '../../i18n.js'
import { unlock } from '../../sound.js'
import CameraView from './CameraView.vue'
import RunPanel from './RunPanel.vue'
import DevicePanel from './DevicePanel.vue'
import CadViewer from './CadViewer.vue'

const expanded = ref(null)
const starting = ref(false)
const startError = ref('')

const streams = computed(() => store.config.streams)
const rows = computed(() => {
  const byCam = {}
  streams.value.forEach((s) => { (byCam[s.camera] = byCam[s.camera] || []).push(s) })
  return Object.values(byCam)
})
// The IV3 photographs the machine's screen; its regions mark the fields to read later.
const keyence = computed(() => streams.value.find((s) => s.kind === 'keyence') || null)
const blockers = computed(() => (store.status ? store.status.blockers : []))
const warnings = computed(() => (store.status ? store.status.warnings : []))
const canStart = computed(() => store.status && store.status.state !== 'starting' && !blockers.value.length && !starting.value)
// Size the grid so all previews fit on screen without scrolling.
const gridStyle = computed(() => {
  const n = rows.value.length || 1
  const widest = Math.max(...rows.value.map((r) => r.reduce((a, s) => a + s.width / s.height, 0)), 1)
  const chrome = 56 + 2 + 32 + 28 + 56 + n * 36
  return { maxWidth: `calc((100vh - ${chrome}px) / ${n} * ${widest.toFixed(3)} + ${12 * (rows.value[0].length - 1)}px)` }
})
const expandedStream = computed(() => streams.value.find((s) => s.name === expanded.value))

const pending = {}
function saveRegions (stream, regions) {
  clearTimeout(pending[stream])
  pending[stream] = setTimeout(async () => {
    try {
      store.draft = await api.saveRegions(stream, regions)
    } catch (e) {
      startError.value = errorText(e)
    }
  }, 100)
}

async function start () {
  unlock()
  starting.value = true
  startError.value = ''
  try {
    await api.start()
  } catch (e) {
    startError.value = errorText(e)
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <div class="setup">
    <section class="previews panel panel-pad">
      <div class="panel-head">
        <h2>{{ t('setup.previews') }}</h2>
        <p class="small muted hint">{{ t('setup.hint') }}</p>
      </div>
      <div class="cam-grid" :style="gridStyle">
      <div v-for="(row, i) in rows" :key="i" class="row">
        <CameraView v-for="s in row" :key="s.name" :stream="s" :regions="store.draft.regions[s.name] || []"
                    :interval="store.config.preview_interval_ms" :matrix-interval="store.config.thermal_matrix_ms"
                    @regions="(r) => saveRegions(s.name, r)" @expand="expanded = s.name" />
      </div>
      <div v-if="keyence" class="row keyence">
        <CameraView :stream="keyence" :regions="store.draft.regions.keyence || []"
                    :interval="store.config.preview_interval_ms"
                    @regions="(r) => saveRegions('keyence', r)" @expand="expanded = 'keyence'" />
        <p class="small muted khint">{{ t('setup.keyenceHint') }}</p>
      </div>
      </div>
    </section>

    <aside class="rail">
      <div class="panel panel-pad"><RunPanel /></div>
      <div class="panel panel-pad"><DevicePanel /></div>
      <div class="panel panel-pad"><CadViewer /></div>
      <div class="startbox panel panel-pad">
        <ul v-if="blockers.length || warnings.length" class="issues">
          <li v-for="(b, i) in blockers" :key="'b' + i" class="blocker"><span class="dot fault"></span>{{ blockerText(b) }}</li>
          <li v-for="(w, i) in warnings" :key="'w' + i" class="warning"><span class="dot warn"></span>{{ warningText(w) }}</li>
        </ul>
        <p v-if="startError" class="small err" role="alert">{{ startError }}</p>
        <button class="btn primary lg start" :disabled="!canStart" @click="start">
          <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="currentColor"/></svg>
          {{ starting ? t('setup.startingBtn') : t('setup.start') }}
        </button>
      </div>
    </aside>

    <div v-if="expandedStream" class="expanded">
      <CameraView :key="'x' + expandedStream.name" :stream="expandedStream" :regions="store.draft.regions[expandedStream.name] || []"
                  :interval="store.config.preview_interval_ms" :matrix-interval="store.config.thermal_matrix_ms" large
                  @regions="(r) => saveRegions(expandedStream.name, r)" @shrink="expanded = null" />
    </div>
  </div>
</template>

<style scoped>
.setup {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: var(--gap);
  align-items: start;
  position: relative;
}
.previews { min-width: 0; }
.previews .panel-head { flex-wrap: wrap; }
.previews .panel-head h2 { flex: 0 0 auto; }
.hint { flex: 1 1 380px; max-width: 80ch; }
.cam-grid { margin: 0 auto; min-width: 560px; }
.row.keyence { align-items: flex-start; }
.row.keyence > :deep(.cv) { flex-grow: 0; flex-basis: 46%; }
.khint { flex: 1 1 40%; padding-top: 34px; }
.row { display: flex; gap: var(--gap); }
.row + .row { margin-top: 6px; }
.rail {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  position: sticky;
  top: var(--pad);
  max-height: calc(100vh - var(--header) - 2 * var(--pad));
  overflow-y: auto;
  padding-bottom: 2px;
}
.startbox { position: sticky; bottom: 0; box-shadow: var(--shadow-1), 0 -8px 16px -8px rgba(9, 29, 45, .12); }
.issues { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.issues li { display: flex; gap: 9px; align-items: baseline; font-size: var(--fs-sm); }
.issues .dot { transform: translateY(-1px); }
.issues .warning .dot { transform: translateY(-1px) rotate(45deg) scale(.85); }
.blocker { color: var(--fault-ink); font-weight: 500; }
.warning { color: var(--ink-2); }
.start { width: 100%; }
.start svg { width: 12px; height: 12px; }
.err { color: var(--fault); margin-bottom: 10px; }
.expanded {
  position: fixed;
  top: calc(var(--header) + 2px);
  left: 0;
  right: calc(390px + var(--pad));
  bottom: 0;
  z-index: 50;
  background: var(--bg);
  padding: var(--pad) var(--gap) var(--pad) var(--pad);
  overflow: auto;
}
@media (max-width: 1280px) {
  .setup { grid-template-columns: minmax(0, 1fr) 340px; }
  .expanded { right: calc(340px + var(--pad)); }
}
</style>
