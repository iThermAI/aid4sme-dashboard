<script setup>
import { computed, ref } from 'vue'
import { store, reloadDraft } from '../../store.js'
import { api } from '../../api.js'
import { t, stopReasonText, errorText } from '../../i18n.js'
import { clock, incrementTrailing, runNo } from '../../format.js'
import VerificationTable from './VerificationTable.vue'

const rec = computed(() => store.status.recording || {})
const result = computed(() => store.status.result || {})
const ok = computed(() => result.value.overall_pass)
const verdict = ref('')
const reason = ref('')
const saved = ref(false)
const error = ref('')
const busy = ref(false)

const changes = computed(() => {
  const inc = (store.status.prefs && store.status.prefs.auto_increment) || []
  const md = (store.draft && store.draft.metadata) || {}
  if (!ok.value) return []
  return inc.filter((f) => md[f] && incrementTrailing(md[f]) !== md[f]).map((f) => ({ f, v: incrementTrailing(md[f]) }))
})

async function setVerdict (v) {
  verdict.value = verdict.value === v ? '' : v
  await saveVerdict()
}
async function saveVerdict () {
  try {
    await api.verdict(rec.value.session_id, verdict.value, reason.value)
    saved.value = true
    error.value = ''
  } catch (e) { error.value = errorText(e) }
}
async function next () {
  busy.value = true
  try {
    if (reason.value && verdict.value) await saveVerdict()
    await api.acknowledge()
    await reloadDraft()
  } catch (e) {
    error.value = errorText(e)
  } finally { busy.value = false }
}
</script>

<template>
  <div class="summary">
    <section class="head panel" :class="ok ? 'good' : 'badrun'">
      <div class="headline">
        <span class="icon" aria-hidden="true">
          <svg v-if="ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 7v6M12 16.5v.5"/></svg>
        </span>
        <div>
          <h1>{{ ok ? t('summary.ok') : t('summary.bad') }}</h1>
          <p class="muted num sub">
            <span class="strong">{{ t('rec.run', { n: runNo(rec.run_number) }) }}</span>
            <span v-if="rec.mould_id">{{ rec.mould_id }}</span>
            <span>{{ t('summary.recorded', { t: clock(rec.elapsed_s) }) }}</span>
            <span>{{ stopReasonText(rec.stop_reason) }}</span>
          </p>
          <p class="xs muted folder num">{{ t('summary.folder') }}: {{ rec.folder }}</p>
          <p v-if="!ok" class="small hint">{{ t('summary.badHint') }}</p>
        </div>
      </div>
      <div class="next">
        <button class="btn primary lg" :disabled="busy" @click="next">{{ t('summary.next') }}</button>
        <p class="xs muted">{{ t('summary.nextKeeps') }}</p>
        <p v-for="c in changes" :key="c.f" class="xs change">{{ t('summary.willChange', { f: t('field.' + c.f), v: c.v }) }}</p>
      </div>
    </section>

    <section class="panel panel-pad verdict">
      <h2>{{ t('summary.verdict') }}</h2>
      <div class="choices" role="group">
        <button class="choice usable" :aria-pressed="verdict === 'usable'" @click="setVerdict('usable')">{{ t('summary.usable') }}</button>
        <button class="choice unsure" :aria-pressed="verdict === 'unsure'" @click="setVerdict('unsure')">{{ t('summary.unsure') }}</button>
        <button class="choice discard" :aria-pressed="verdict === 'discard'" @click="setVerdict('discard')">{{ t('summary.discard') }}</button>
      </div>
      <label class="field reason">
        <span class="label">{{ t('summary.reason') }}</span>
        <input v-model="reason" type="text" maxlength="500" :placeholder="t('summary.reasonPlaceholder')" @change="verdict && saveVerdict()" />
      </label>
      <p v-if="saved && verdict" class="xs ok-text">{{ t('summary.verdictSaved') }}</p>
      <p v-if="error" class="small err">{{ error }}</p>
    </section>

    <section class="panel">
      <VerificationTable :result="result" />
    </section>
  </div>
</template>

<style scoped>
.summary { display: flex; flex-direction: column; gap: var(--gap); max-width: 1280px; }
.head { display: flex; justify-content: space-between; gap: 24px; padding: 20px 24px; border-left: 5px solid var(--ok); }
.head.badrun { border-left-color: var(--fault); }
.headline { display: flex; gap: 16px; align-items: flex-start; }
.icon { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--ok-soft); color: var(--ok); flex: 0 0 auto; }
.badrun .icon { background: var(--fault-soft); color: var(--fault); }
.icon svg { width: 22px; height: 22px; }
h1 { font-size: var(--fs-2xl); }
.sub { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 4px; }
.strong { color: var(--ink); font-weight: 600; }
.folder { margin-top: 6px; word-break: break-all; }
.hint { margin-top: 8px; max-width: 70ch; }
.next { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; text-align: right; }
.change { color: var(--primary); font-weight: 600; }
.verdict h2 { margin-bottom: 10px; }
.choices { display: flex; gap: 8px; margin-bottom: 12px; }
.choice {
  min-width: 140px;
  min-height: 42px;
  border-radius: var(--r-sm);
  border: 1.5px solid var(--line-strong);
  background: var(--surface);
  font-weight: 600;
  cursor: pointer;
}
.choice:hover { border-color: var(--muted); }
.choice.usable[aria-pressed="true"] { background: var(--ok); border-color: var(--ok); color: #fff; }
.choice.unsure[aria-pressed="true"] { background: var(--warn); border-color: var(--warn); color: #fff; }
.choice.discard[aria-pressed="true"] { background: var(--fault); border-color: var(--fault); color: #fff; }
.reason { max-width: 560px; }
.ok-text { color: var(--ok); margin-top: 6px; }
.err { color: var(--fault); margin-top: 6px; }
</style>
