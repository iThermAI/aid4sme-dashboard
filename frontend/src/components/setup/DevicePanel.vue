<script setup>
import { computed } from 'vue'
import { store } from '../../store.js'
import { t, camName } from '../../i18n.js'

const devices = computed(() => (store.status ? store.status.devices : []))
const clockLimit = 2
function clockOff (d) { return d.drift_s !== undefined && d.drift_s !== null && Math.abs(d.drift_s) > clockLimit }
function signed (v) { return (v > 0 ? '+' : '') + v }
</script>

<template>
  <section>
    <div class="panel-head">
      <h2>{{ t('setup.devices') }}</h2>
      <button class="link small" @click="store.view = 'cameras'">{{ t('nav.cameras') }}</button>
    </div>
    <ul class="list">
      <li v-for="d in devices" :key="d.id">
        <div class="row1">
          <span class="dot" :class="d.reachable === false ? 'fault' : d.reachable ? '' : 'idle'"></span>
          <span class="name">{{ camName(d.id) }}</span>
          <span class="muted small num">{{ d.ip }}</span>
          <span class="state small" :class="{ bad: d.reachable === false }">
            {{ d.reachable === false ? t('setup.offline') : d.reachable ? t('setup.online') : t('setup.checking') }}
          </span>
        </div>
        <div v-if="d.reachable" class="row2 small">
          <span :class="clockOff(d) ? 'w' : 'muted'">{{ clockOff(d) ? t('setup.clockOff', { v: signed(d.drift_s) }) : t('setup.clockOk') }}</span>
          <button v-if="d.reference_changes" class="chip warn" @click="store.view = 'cameras'">{{ t('setup.settingsChanged', { n: d.reference_changes }) }}</button>
          <button v-else-if="d.warnings" class="chip warn" @click="store.view = 'cameras'">{{ t('setup.settingsWarn', { n: d.warnings }) }}</button>
          <span v-else class="muted">{{ t('setup.settingsOk') }}</span>
        </div>
      </li>
      <li v-if="store.config.keyence_mode === 'off'">
        <div class="row1">
          <span class="dot idle"></span>
          <span class="name">{{ t('stream.keyence') }}</span>
          <span class="state small muted">{{ t('setup.keyenceNone') }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.list { list-style: none; margin: 0; padding: 0; }
.list li { padding: 7px 0; border-top: 1px solid var(--line); }
.list li:first-child { border-top: 0; padding-top: 0; }
.row1 { display: flex; align-items: center; gap: 8px; }
.name { font-weight: 500; }
.state { margin-left: auto; }
.state.bad { color: var(--fault); font-weight: 600; }
.row2 { display: flex; gap: 10px; align-items: center; padding-left: 16px; margin-top: 2px; }
.w { color: var(--warn-ink); }
.chip { border: 0; cursor: pointer; border-radius: 999px; padding: 0 8px; font-size: var(--fs-xs); font-weight: 600; }
.chip.warn { background: var(--warn-soft); color: var(--warn-ink); }
</style>
