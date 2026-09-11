<script setup>
import { onMounted, ref } from 'vue'
import { savePrefs } from '../../store.js'
import { api } from '../../api.js'
import { t, camName, errorText } from '../../i18n.js'
import { dateTime } from '../../format.js'
import Modal from '../ui/Modal.vue'

const emit = defineEmits(['changed'])
const list = ref([])
const error = ref('')
const busy = ref(false)

async function load () {
  try { list.value = await api.profiles() } catch (e) { error.value = errorText(e) }
}
onMounted(load)

// ---- save ------------------------------------------------------------------------
const saving = ref(false)
const name = ref('')
const note = ref('')
const makeRef = ref(true)
function openSave () {
  name.value = ''
  note.value = ''
  makeRef.value = !list.value.some((p) => p.is_reference)
  saving.value = true
}
async function save () {
  busy.value = true
  try {
    await api.saveProfile(name.value, note.value, makeRef.value)
    saving.value = false
    error.value = ''
    await load()
    emit('changed')
  } catch (e) { error.value = errorText(e) } finally { busy.value = false }
}

async function useReference (p) {
  try {
    await savePrefs({ reference_profile: p.is_reference ? null : p.slug })
    await load()
    emit('changed')
  } catch (e) { error.value = errorText(e) }
}
async function remove (p) {
  if (!window.confirm(t('profiles.deleteConfirm', { n: p.name }))) return
  try { await api.deleteProfile(p.slug); await load(); emit('changed') } catch (e) { error.value = errorText(e) }
}

// ---- restore -------------------------------------------------------------------------
const restoring = ref(null)
const preview = ref(null)
const chosen = ref([])
const report = ref(null)
async function openRestore (p) {
  restoring.value = p
  preview.value = null
  report.value = null
  chosen.value = p.cameras.slice()
  try { preview.value = await api.profilePreview(p.slug) } catch (e) { error.value = errorText(e); restoring.value = null }
}
async function doRestore () {
  busy.value = true
  try {
    report.value = await api.restoreProfile(restoring.value.slug, chosen.value)
    emit('changed')
  } catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
</script>

<template>
  <section class="panel panel-pad profiles">
    <div class="panel-head">
      <h2>{{ t('profiles.title') }}</h2>
      <button class="btn sm primary" :disabled="busy" @click="openSave">{{ t('profiles.saveNew') }}</button>
    </div>
    <p class="small muted intro">{{ t('profiles.intro') }}</p>
    <p v-if="error" class="small err">{{ error }}</p>

    <div v-if="saving" class="saveform">
      <label class="field"><span class="label">{{ t('profiles.name') }}</span><input v-model="name" maxlength="80" @keydown.enter="save" /></label>
      <label class="field"><span class="label">{{ t('profiles.note') }} <span class="hint">{{ t('common.optional') }}</span></span><input v-model="note" maxlength="200" /></label>
      <label class="check"><input v-model="makeRef" type="checkbox" /> {{ t('profiles.makeReference') }}</label>
      <div class="row">
        <button class="btn sm primary" :disabled="busy || !name.trim()" @click="save">{{ busy ? t('common.saving') : t('common.save') }}</button>
        <button class="btn sm ghost" @click="saving = false">{{ t('common.cancel') }}</button>
      </div>
    </div>

    <p v-if="!list.length && !saving" class="small muted empty">{{ t('profiles.empty') }}</p>
    <ul v-else class="plist">
      <li v-for="p in list" :key="p.slug" :class="{ ref: p.is_reference }">
        <div class="pmain">
          <span class="pname">{{ p.name }}</span>
          <span v-if="p.is_reference" class="badge brand">{{ t('profiles.reference') }}</span>
          <span class="xs muted num">{{ t('profiles.created', { t: dateTime(p.created_at) }) }}</span>
          <span v-if="p.note" class="xs muted pnote">{{ p.note }}</span>
        </div>
        <div class="pacts">
          <button class="link small" @click="useReference(p)">{{ p.is_reference ? t('profiles.clearReference') : t('profiles.useReference') }}</button>
          <button class="btn sm" @click="openRestore(p)">{{ t('profiles.restore') }}</button>
          <button class="btn sm ghost icon" :aria-label="t('common.delete')" :title="t('common.delete')" @click="remove(p)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5"/></svg>
          </button>
        </div>
      </li>
    </ul>

    <Modal v-if="restoring" wide :title="t('profiles.restoreTitle', { n: restoring.name })" @close="restoring = null">
      <p v-if="!preview" class="muted">{{ t('common.loading') }}</p>
      <template v-else-if="!report">
        <p class="small">{{ t('profiles.restoreIntro') }}</p>
        <div v-for="(c, cid) in preview.cameras" :key="cid" class="cam">
          <label class="check strong"><input v-model="chosen" type="checkbox" :value="cid" :disabled="!c.reachable" /> {{ camName(cid) }}</label>
          <p v-if="!c.reachable" class="small err">{{ t('setup.offline') }}</p>
          <p v-else-if="!c.changes.length" class="small muted">{{ t('profiles.noChanges') }}</p>
          <table v-else class="data small">
            <tr v-for="(ch, i) in c.changes" :key="i">
              <td class="muted">{{ ch.section }}</td><td class="num">{{ ch.key }}</td>
              <td class="num cur">{{ ch.new === null ? '\u2013' : ch.new }}</td><td>→</td>
              <td class="num tgt">{{ ch.old === null ? '\u2013' : ch.old }}</td>
            </tr>
          </table>
        </div>
      </template>
      <template v-else>
        <p class="notice ok">{{ t('profiles.restored') }}</p>
        <div v-for="(r, cid) in report" :key="cid" class="cam">
          <p class="strong">{{ camName(cid) }}</p>
          <ul class="res small">
            <li v-for="x in r.results" :key="x.section" :class="{ bad: !x.ok }">{{ x.ok ? '\u2713' : '\u2717' }} {{ x.section }} <span class="muted">HTTP {{ x.http }} {{ x.message }}</span></li>
          </ul>
          <p v-if="r.remaining_changes.length" class="small err">{{ t('profiles.remaining', { n: r.remaining_changes.length }) }}
            <span v-for="(ch, i) in r.remaining_changes" :key="i" class="num"> {{ ch.key }}</span></p>
        </div>
      </template>
      <template #footer>
        <button class="btn ghost" @click="restoring = null">{{ report ? t('common.close') : t('common.cancel') }}</button>
        <button v-if="!report" class="btn primary" :disabled="busy || !preview || !chosen.length" @click="doRestore">
          {{ busy ? t('common.saving') : t('profiles.restoreBtn') }}
        </button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.intro { max-width: 90ch; margin-bottom: 10px; }
.saveform { display: grid; grid-template-columns: 1fr 1.4fr auto auto; gap: 10px; align-items: end; padding: 12px; margin-bottom: 10px; background: var(--surface-2); border-radius: var(--r-sm); }
.check { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); padding-bottom: 8px; }
.check input { width: 16px; height: 16px; min-height: 0; }
.row { display: flex; gap: 6px; }
.empty { padding: 8px 0; }
.plist { list-style: none; margin: 0; padding: 0; }
.plist li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 10px; border-top: 1px solid var(--line); }
.plist li.ref { background: var(--primary-soft); border-radius: var(--r-sm); border-top-color: transparent; }
.pmain { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; min-width: 0; }
.pname { font-weight: 600; }
.pnote { max-width: 40ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pacts { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.cam { margin-top: 14px; }
.cur { color: var(--warn-ink); }
.tgt { color: var(--ok); font-weight: 600; }
.res { list-style: none; padding: 0; margin: 4px 0; }
.res .bad { color: var(--fault); }
.strong { font-weight: 600; }
.err { color: var(--fault); }
</style>
