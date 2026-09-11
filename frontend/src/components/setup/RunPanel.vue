<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { store } from '../../store.js'
import { api } from '../../api.js'
import { t, errorText } from '../../i18n.js'
import { runNo } from '../../format.js'

const md = reactive({ operator: '', mould_id: '', part_number: '', material: '', shot_counter_start: '', thermal_range: '', notes: '' })
Object.assign(md, store.draft.metadata || {})
const saveState = ref('')
const error = ref('')
let timer = null

const required = computed(() => (store.config ? store.config.required_metadata : []))
const autoInc = computed(() => ((store.status && store.status.prefs && store.status.prefs.auto_increment) || []))
const nextRun = computed(() => (store.status ? store.status.next_run : 1))

watch(md, () => {
  saveState.value = 'saving'
  clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      store.draft = await api.saveMetadata({ ...md })
      saveState.value = 'saved'
      error.value = ''
    } catch (e) {
      saveState.value = ''
      error.value = errorText(e)
    }
  }, 400)
}, { deep: true })

// The draft changes from outside after a run (automatic increments) or a preset.
watch(() => store.draft && store.draft.updated_at, () => {
  const d = store.draft.metadata || {}
  if (saveState.value !== 'saving') Object.keys(md).forEach((k) => { if ((d[k] || '') !== md[k]) md[k] = d[k] || '' })
})

// ---- part presets ------------------------------------------------------------
const presets = ref([])
const presetSlug = ref(store.draft.part_preset || '')
const saving = ref(false)
const presetName = ref('')
async function loadPresets () {
  try { presets.value = await api.parts() } catch (e) { /* keep list */ }
}
async function applyPreset () {
  if (!presetSlug.value) return
  try {
    store.draft = await api.applyPart(presetSlug.value)
    Object.assign(md, store.draft.metadata)
    error.value = ''
  } catch (e) { error.value = errorText(e) }
}
async function savePreset () {
  try {
    const r = await api.savePart(presetName.value || md.part_number)
    store.draft = r.draft
    presetSlug.value = r.slug
    saving.value = false
    await loadPresets()
  } catch (e) { error.value = errorText(e) }
}
function openSave () {
  presetName.value = md.part_number ? `${md.part_number}${md.material ? ' ' + md.material : ''}` : ''
  saving.value = true
}
onMounted(loadPresets)

// ---- planned stop ---------------------------------------------------------------
const STOP_CHOICES = [0, 60, 120, 180, 300, 600]
const stopAfter = ref(String((store.draft.options && store.draft.options.stop_after_s) || 0))
const custom = ref(!STOP_CHOICES.includes(Number(stopAfter.value)))
const customMin = ref(custom.value ? Math.round(Number(stopAfter.value) / 60) : 4)
async function saveStop () {
  const seconds = custom.value ? Math.round(Number(customMin.value || 0) * 60) : Number(stopAfter.value)
  try {
    store.draft = await api.saveOptions({ stop_after_s: seconds })
    error.value = ''
  } catch (e) { error.value = errorText(e) }
}
function onStopChoice () {
  custom.value = stopAfter.value === 'custom'
  saveStop()
}

const fields = [['operator', 'text'], ['material', 'text'], ['mould_id', 'text'], ['part_number', 'text']]
</script>

<template>
  <section class="run">
    <div class="panel-head">
      <h2>{{ t('setup.runDetails') }}</h2>
      <span class="xs muted">{{ saveState === 'saving' ? t('common.saving') : saveState === 'saved' ? t('common.saved') : '' }}</span>
    </div>

    <div class="preset">
      <label class="field grow">
        <span class="label">{{ t('setup.preset') }}</span>
        <select v-model="presetSlug" @change="applyPreset">
          <option value="">{{ t('setup.presetNone') }}</option>
          <option v-for="p in presets" :key="p.slug" :value="p.slug">{{ p.name }}</option>
        </select>
      </label>
      <button v-if="!saving" class="btn sm save-preset" :title="t('setup.presetHint')" @click="openSave">{{ t('setup.presetSave') }}</button>
    </div>
    <div v-if="saving" class="preset-save">
      <input v-model="presetName" :placeholder="t('setup.presetName')" :aria-label="t('setup.presetName')" @keydown.enter="savePreset" />
      <button class="btn sm primary" @click="savePreset">{{ t('common.save') }}</button>
      <button class="btn sm ghost" @click="saving = false">{{ t('common.cancel') }}</button>
    </div>

    <div class="runno">
      <span class="readout big num">{{ t('setup.runNumber', { n: runNo(nextRun) }) }}</span>
      <span class="small muted">{{ md.mould_id ? t('setup.runOfMould', { m: md.mould_id }) : t('setup.runNoMould') }}</span>
    </div>

    <div class="grid">
      <label v-for="[f] in fields" :key="f" class="field">
        <span class="label">
          {{ t('field.' + f) }}
          <span v-if="autoInc.includes(f)" class="inc" :title="t('setup.autoInc')" :aria-label="t('setup.autoInc')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 8a5 5 0 0 1 8.6-3.5M13 3v3h-3M13 8a5 5 0 0 1-8.6 3.5M3 13v-3h3"/></svg>
          </span>
        </span>
        <input v-model.trim="md[f]" type="text" autocomplete="off" :aria-required="required.includes(f)" />
      </label>
      <label class="field">
        <span class="label">
          {{ t('field.shot_counter_start') }}
          <span v-if="autoInc.includes('shot_counter_start')" class="inc" :title="t('setup.autoInc')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 8a5 5 0 0 1 8.6-3.5M13 3v3h-3M13 8a5 5 0 0 1-8.6 3.5M3 13v-3h3"/></svg>
          </span>
        </span>
        <input v-model.trim="md.shot_counter_start" type="text" inputmode="numeric" autocomplete="off" :placeholder="t('common.optional')" />
      </label>
      <label class="field">
        <span class="label">{{ t('setup.stopAfter') }}</span>
        <div class="stop">
          <select v-model="stopAfter" @change="onStopChoice">
            <option value="0">{{ t('setup.manualStop') }}</option>
            <option v-for="s in STOP_CHOICES.slice(1)" :key="s" :value="String(s)">{{ s / 60 }} {{ t('common.minutes') }}</option>
            <option value="custom">{{ t('setup.customMinutes') }}</option>
          </select>
          <input v-if="custom" v-model="customMin" type="number" min="1" max="30" step="1" class="mins" :aria-label="t('common.minutes')" @change="saveStop" />
        </div>
      </label>
      <label class="field span2">
        <span class="label">{{ t('field.thermal_range') }}</span>
        <div class="segmented" role="group">
          <button v-for="(r, key) in store.config.thermal_ranges" :key="key" type="button"
                  :aria-pressed="md.thermal_range === key" @click="md.thermal_range = key">{{ r.label }}</button>
        </div>
      </label>
      <label class="field span2">
        <span class="label">{{ t('field.notes') }} <span class="hint">{{ t('common.optional') }}</span></span>
        <textarea v-model="md.notes" rows="2"></textarea>
      </label>
    </div>
    <p v-if="error" class="small err">{{ error }}</p>
  </section>
</template>

<style scoped>
.preset { display: flex; align-items: flex-end; gap: 8px; }
.grow { flex: 1 1 auto; }
.save-preset { flex: 0 0 auto; }
.preset-save { display: flex; gap: 6px; margin-top: 8px; }
.runno {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 12px 0 10px;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  background: var(--primary-soft);
}
.big { font-size: 22px; color: var(--primary); font-weight: 600; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
.span2 { grid-column: span 2; }
.inc { display: inline-flex; color: var(--primary); }
.inc svg { width: 13px; height: 13px; }
.stop { display: flex; gap: 6px; }
.mins { width: 64px; flex: 0 0 64px; }
.err { color: var(--fault); margin-top: 8px; }
</style>
