<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { store } from '../../store.js'
import { api } from '../../api.js'
import { t, streamLabel, eventText, errorText } from '../../i18n.js'
import { clock, runNo, timeOfDay } from '../../format.js'
import { alarm, enabled as soundDefault, setEnabled } from '../../sound.js'
import StreamRow from './StreamRow.vue'

const rec = computed(() => store.status.recording || {})
const state = computed(() => store.status.state)
const streams = computed(() => rec.value.streams || [])
const problems = computed(() => streams.value.filter((s) => s.health === 'dead' || s.health === 'stalled'))
const saturated = computed(() => streams.value.filter((s) => s.type === 'radiometric' && s.saturated > 0))
const rangeLabel = computed(() => {
  const md = store.draft && store.draft.metadata
  const r = md && store.config.thermal_ranges[md.thermal_range]
  return r ? r.label : ''
})
const planned = computed(() => rec.value.stop_after_s || 0)
const limit = computed(() => planned.value || rec.value.max_s || 0)
const progress = computed(() => (planned.value ? Math.min(1, (rec.value.elapsed_s || 0) / planned.value) : 0))

// ---- stop (two clicks, so a stray click cannot end a run) --------------------
const armed = ref(false)
let armTimer = null
const stopError = ref('')
async function stop () {
  if (!armed.value) {
    armed.value = true
    armTimer = setTimeout(() => { armed.value = false }, 4000)
    return
  }
  clearTimeout(armTimer)
  armed.value = false
  try {
    await api.stop()
  } catch (e) {
    stopError.value = errorText(e)
  }
}

// ---- notes --------------------------------------------------------------------
const note = ref('')
const noteError = ref('')
async function addNote () {
  const text = note.value.trim()
  if (!text) return
  try {
    await api.note(text)
    note.value = ''
    noteError.value = ''
  } catch (e) {
    noteError.value = errorText(e)
  }
}

// ---- alarm sound when a stream fails ----------------------------------------------
const sound = ref(soundDefault)
function toggleSound () { sound.value = !sound.value; setEnabled(sound.value) }
let alarmTimer = null
watch(() => problems.value.length, (n, before) => {
  clearInterval(alarmTimer)
  if (n > 0) {
    if (n > (before || 0)) alarm()
    alarmTimer = setInterval(alarm, 15000)
  }
})
onBeforeUnmount(() => { clearTimeout(armTimer); clearInterval(alarmTimer) })
</script>

<template>
  <section class="rec">
    <header class="band" :class="{ closing: state !== 'recording' }">
      <div class="left">
        <span class="elapsed readout" aria-live="off">{{ clock(rec.elapsed_s) }}</span>
        <div class="about">
          <p class="what">
            <span v-if="state === 'recording'" class="pulse" aria-hidden="true"></span>
            {{ state === 'recording' ? t('rec.recording') : t('rec.closing.' + state) }}
          </p>
          <p class="sub num">
            <span class="runtag">{{ t('rec.run', { n: runNo(rec.run_number) }) }}</span>
            <span v-if="rec.mould_id">{{ rec.mould_id }}</span>
            <span class="sid">{{ rec.session_id }}</span>
          </p>
          <div v-if="state === 'recording'" class="limit">
            <div v-if="planned" class="track"><span :style="{ width: progress * 100 + '%' }"></span></div>
            <span class="sub">{{ planned ? t('rec.plannedStop', { t: clock(limit) }) : t('rec.stopsAt', { t: clock(limit) }) }}</span>
          </div>
        </div>
      </div>
      <div class="right">
        <button class="sound" :aria-pressed="sound" :title="sound ? t('rec.soundOn') : t('rec.soundOff')" @click="toggleSound">
          <svg v-if="sound" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 6h2.5L9 3v10L5.5 10H3zM11.5 5.5a3.5 3.5 0 0 1 0 5M13 4a5.5 5.5 0 0 1 0 8"/></svg>
          <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 6h2.5L9 3v10L5.5 10H3zM11 6l4 4M15 6l-4 4"/></svg>
        </button>
        <button v-if="state === 'recording'" class="stop" :class="{ armed }" @click="stop">
          <span class="sq" aria-hidden="true"></span>{{ armed ? t('rec.confirmStop') : t('rec.stop') }}
        </button>
        <p v-if="stopError" class="small">{{ stopError }}</p>
      </div>
    </header>

    <div class="content">
      <p v-for="p in problems" :key="p.name" class="notice fault" role="alert">
        {{ t(p.health === 'dead' ? 'rec.streamDown' : 'rec.streamStalled', { s: streamLabel(p.name) }) }}
      </p>
      <p v-if="saturated.length" class="notice warn" role="alert">
        {{ t('rec.saturated', { s: saturated.map((s) => streamLabel(s.name)).join(', '), r: rangeLabel }) }}
      </p>

      <div class="panel">
        <table class="data">
          <thead>
            <tr>
              <th>{{ t('rec.table.stream') }}</th><th>{{ t('rec.table.status') }}</th>
              <th class="r">{{ t('rec.table.rate') }}</th><th class="r">{{ t('rec.table.written') }}</th>
              <th class="r">{{ t('rec.table.last') }}</th><th>{{ t('rec.table.minute') }}</th><th>{{ t('rec.table.details') }}</th>
            </tr>
          </thead>
          <tbody>
            <StreamRow v-for="s in streams" :key="s.name" :s="s" :nominal="store.config.nominal_fps" />
          </tbody>
        </table>
      </div>

      <div class="lower">
        <section class="panel panel-pad">
          <div class="panel-head"><h2>{{ t('rec.notes') }}</h2></div>
          <p class="small muted">{{ t('rec.notesHint') }}</p>
          <div class="noteform">
            <input v-model="note" type="text" maxlength="500" :placeholder="t('rec.notePlaceholder')" :aria-label="t('rec.notes')"
                   :disabled="state !== 'recording'" @keydown.enter="addNote" />
            <button class="btn" :disabled="state !== 'recording' || !note.trim()" @click="addNote">{{ t('rec.addNote') }}</button>
          </div>
          <p v-if="noteError" class="small err">{{ noteError }}</p>
          <ul class="log">
            <li v-for="(m, i) in (rec.marks || []).slice().reverse()" :key="i">
              <span class="num muted">{{ timeOfDay(m.t_iso) }}</span><span>{{ m.note }}</span>
            </li>
          </ul>
        </section>
        <section class="panel panel-pad">
          <div class="panel-head"><h2>{{ t('rec.events') }}</h2></div>
          <ul class="log">
            <li v-for="(e, i) in (rec.events || []).slice().reverse()" :key="i" :class="{ w: e.level === 'warning' }">
              <span class="num muted">{{ timeOfDay(e.t_iso) }}</span>
              <span>{{ eventText(e) }}<template v-if="e.stream"> – {{ streamLabel(e.stream) }}</template></span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.rec { margin: 0 calc(-1 * var(--pad)); }
.band {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  padding: 18px 28px 22px;
  background: var(--rec-band);
  color: #fff;
  box-shadow: inset 0 -2px 0 #17aafe;
}
.band.closing { box-shadow: inset 0 -2px 0 #4b6a86; }
.left { display: flex; align-items: center; gap: 30px; min-width: 0; }
.elapsed { font-size: var(--fs-hero); line-height: .95; letter-spacing: -.01em; font-weight: 500; }
.what { display: flex; align-items: center; gap: 10px; font-size: var(--fs-xl); font-weight: 600; }
.pulse { width: 12px; height: 12px; border-radius: 50%; background: #17aafe; box-shadow: 0 0 0 0 rgba(23, 170, 254, .6); animation: pulse 1.8s ease-out infinite; }
@keyframes pulse { 70% { box-shadow: 0 0 0 10px rgba(23, 170, 254, 0); } 100% { box-shadow: 0 0 0 0 rgba(23, 170, 254, 0); } }
.sub { color: #a9bdd1; font-size: var(--fs-sm); display: flex; gap: 12px; margin-top: 4px; flex-wrap: wrap; }
.runtag { color: #fff; font-weight: 600; }
.sid { opacity: .8; }
.limit { display: flex; align-items: center; gap: 12px; margin-top: 6px; }
.limit .sub { margin: 0; }
.track { width: 220px; height: 4px; border-radius: 2px; background: rgba(255, 255, 255, .15); overflow: hidden; }
.track span { display: block; height: 100%; background: var(--brand-gradient); transition: width .9s linear; }
.right { display: flex; align-items: center; gap: 14px; }
.sound { width: 40px; height: 40px; border-radius: 50%; border: 1px solid rgba(255, 255, 255, .25); background: transparent; color: #fff; cursor: pointer; display: grid; place-items: center; }
.sound svg { width: 18px; height: 18px; }
.sound:hover { background: rgba(255, 255, 255, .08); }
.stop {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-height: 60px;
  min-width: 250px;
  padding: 10px 26px;
  border-radius: var(--r-md);
  border: 0;
  background: #fff;
  color: #9e1c1c;
  font-size: var(--fs-lg);
  font-weight: 600;
  cursor: pointer;
}
.stop:hover { background: #fdeaea; }
.stop.armed { background: #c62828; color: #fff; }
.sq { width: 14px; height: 14px; border-radius: 2px; background: currentColor; }
.content { padding: var(--pad); display: flex; flex-direction: column; gap: var(--gap); }
.lower { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }
.noteform { display: flex; gap: 8px; margin: 10px 0 8px; }
.log { list-style: none; margin: 0; padding: 0; font-size: var(--fs-sm); max-height: 170px; overflow-y: auto; }
.log li { display: flex; gap: 12px; padding: 4px 0; border-top: 1px solid var(--line); }
.log li:first-child { border-top: 0; }
.log li.w { color: var(--warn-ink); font-weight: 500; }
.err { color: var(--fault); }
</style>
