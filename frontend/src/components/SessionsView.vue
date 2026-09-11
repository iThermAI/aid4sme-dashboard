<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api.js'
import { t, errorText, stopReasonText } from '../i18n.js'
import { clock, dateTime, mb, runNo } from '../format.js'

const rows = ref([])
const loading = ref(true)
const error = ref('')
const query = ref('')
const open = ref(null)
const detail = ref(null)

async function load () {
  loading.value = true
  try {
    rows.value = await api.sessions()
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((r) => [r.mould_id, r.part_number, r.material, r.operator, r.session_id]
    .some((v) => (v || '').toLowerCase().includes(q)))
})

const STATUS_CLASS = { complete: 'ok', check: 'warn', failed: 'fault', interrupted: 'fault', recording: 'brand' }

async function setVerdict (row, value) {
  try {
    const v = await api.verdict(row.session_id, value, '')
    row.verdict = v ? v.verdict : null
  } catch (e) { error.value = errorText(e) }
}

async function toggle (row) {
  if (open.value === row.session_id) { open.value = null; return }
  open.value = row.session_id
  detail.value = null
  try { detail.value = await api.session(row.session_id) } catch (e) { error.value = errorText(e) }
}
</script>

<template>
  <section class="sessions">
    <div class="top">
      <h1>{{ t('sessions.title') }}</h1>
      <span class="muted small">{{ t('sessions.count', { n: filtered.length }) }}</span>
      <input v-model="query" class="search" type="text" :placeholder="t('sessions.search')" :aria-label="t('sessions.search')" />
      <button class="btn" @click="load">{{ t('common.refresh') }}</button>
    </div>
    <p v-if="error" class="notice fault">{{ error }}</p>

    <div class="panel">
      <p v-if="loading && !rows.length" class="panel-pad muted">{{ t('common.loading') }}</p>
      <p v-else-if="!rows.length" class="panel-pad muted">{{ t('sessions.empty') }}</p>
      <table v-else class="data">
        <thead>
          <tr>
            <th>{{ t('sessions.started') }}</th><th>{{ t('sessions.mould') }}</th><th class="r">{{ t('sessions.run') }}</th>
            <th>{{ t('sessions.part') }}</th><th>{{ t('sessions.material') }}</th><th>{{ t('sessions.operator') }}</th>
            <th class="r">{{ t('sessions.length') }}</th><th>{{ t('sessions.result') }}</th><th>{{ t('sessions.verdict') }}</th>
            <th class="r">{{ t('sessions.size') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in filtered" :key="r.session_id">
            <tr class="row" :class="{ opened: open === r.session_id }" @click="toggle(r)">
              <td class="num">{{ dateTime(r.started_at) }}<span v-if="r.simulated" class="badge sim">{{ t('sessions.simulated') }}</span></td>
              <td class="strong">{{ r.mould_id || '\u2013' }}</td>
              <td class="r num">{{ r.run_number ? runNo(r.run_number) : '\u2013' }}</td>
              <td>{{ r.part_number || '\u2013' }}</td>
              <td>{{ r.material || '\u2013' }}</td>
              <td>{{ r.operator || '\u2013' }}</td>
              <td class="r num">{{ r.duration_s ? clock(r.duration_s) : '\u2013' }}</td>
              <td><span class="badge" :class="STATUS_CLASS[r.status]">{{ t('sessions.status.' + r.status) }}</span></td>
              <td @click.stop>
                <select class="verdict" :class="r.verdict" :value="r.verdict || ''" :aria-label="t('sessions.verdict')"
                        @change="setVerdict(r, $event.target.value)">
                  <option value="">&ndash;</option>
                  <option value="usable">{{ t('summary.usable') }}</option>
                  <option value="unsure">{{ t('summary.unsure') }}</option>
                  <option value="discard">{{ t('summary.discard') }}</option>
                </select>
              </td>
              <td class="r num">{{ mb(r.size_mb) }}</td>
            </tr>
            <tr v-if="open === r.session_id" class="detail">
              <td colspan="10">
                <p v-if="!detail" class="muted small">{{ t('common.loading') }}</p>
                <div v-else class="dgrid small">
                  <div><span class="muted">{{ t('summary.folder') }}</span><span class="num path">{{ detail.folder }}</span></div>
                  <div><span class="muted">{{ t('sessions.result') }}</span><span>{{ stopReasonText(detail.metadata.stop_reason) }}</span></div>
                  <div v-if="detail.metadata.operator_verdict && detail.metadata.operator_verdict.reason">
                    <span class="muted">{{ t('summary.reason') }}</span><span>{{ detail.metadata.operator_verdict.reason }}</span>
                  </div>
                  <div v-if="(detail.metadata.operator_metadata || {}).notes">
                    <span class="muted">{{ t('field.notes') }}</span><span>{{ detail.metadata.operator_metadata.notes }}</span>
                  </div>
                  <div v-if="(detail.metadata.operator_notes_during_run || []).length">
                    <span class="muted">{{ t('rec.notes') }}</span>
                    <span>{{ detail.metadata.operator_notes_during_run.map((m) => m.note).join(' · ') }}</span>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.sessions { display: flex; flex-direction: column; gap: var(--gap); }
.top { display: flex; align-items: center; gap: 14px; }
.top h1 { font-size: var(--fs-xl); }
.search { margin-left: auto; max-width: 380px; }
.row { cursor: pointer; }
.row:hover td { background: var(--surface-2); }
.row.opened td { background: var(--primary-soft); }
.strong { font-weight: 600; }
.sim { margin-left: 8px; }
.verdict { width: 130px; min-height: 28px; padding: 2px 6px; font-size: var(--fs-sm); }
.verdict.usable { color: var(--ok); font-weight: 600; }
.verdict.discard { color: var(--fault); font-weight: 600; }
.verdict.unsure { color: var(--warn-ink); font-weight: 600; }
.detail td { background: var(--surface-2); }
.dgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; padding: 4px 0; }
.dgrid div { display: flex; gap: 10px; }
.dgrid .muted { flex: 0 0 150px; }
.path { word-break: break-all; }
</style>
