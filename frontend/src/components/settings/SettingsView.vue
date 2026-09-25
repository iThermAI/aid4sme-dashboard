<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { store, savePrefs, loadInitial } from '../../store.js'
import { api } from '../../api.js'
import { t, camName, errorText } from '../../i18n.js'

const conn = ref(null)
const rows = ref([])
const tests = reactive({})
const msg = ref('')
const error = ref('')
const busy = ref(false)

async function load () {
  try {
    conn.value = await api.connections()
    rows.value = conn.value.cameras.map((c) => ({ id: c.id, ip: c.ip, user: c.user, password: '', password_set: c.password_set }))
  } catch (e) { error.value = errorText(e) }
}
onMounted(load)

async function test (r) {
  tests[r.id] = { busy: true }
  try {
    const res = await api.testConnection({ id: r.id, ip: r.ip, user: r.user, password: r.password })
    tests[r.id] = res
  } catch (e) {
    tests[r.id] = { ok: false, text: errorText(e) }
  }
}
function testText (r) {
  const x = tests[r.id]
  if (!x) return ''
  if (x.busy) return t('common.loading')
  if (x.text) return x.text
  if (x.ok) return t('settings.testOk', { m: [x.model, x.name].filter(Boolean).join(', ') })
  if (x.reason === 'unauthorized') return t('settings.testUnauthorized')
  if (x.reason === 'http') return t('settings.testHttp', { v: x.detail })
  return t('settings.testUnreachable')
}

async function saveConnections () {
  busy.value = true
  msg.value = ''
  try {
    await api.saveConnections(rows.value.map((r) => ({ id: r.id, ip: r.ip.trim(), user: r.user.trim(), password: r.password })))
    await load()
    await loadInitial()
    msg.value = t('settings.connectionsSaved')
    error.value = ''
  } catch (e) { error.value = errorText(e) } finally { busy.value = false }
}

const keyence = reactive({ mode: 'off', host: '', port: 8500, trigger: true, trigger_interval_s: 5, ftp_port: 2121 })
const kMsg = ref('')
async function loadKeyence () {
  try {
    const k = await api.keyence()
    Object.keys(keyence).forEach((key) => { if (k[key] !== undefined) keyence[key] = k[key] })
  } catch (e) { /* section stays at defaults */ }
}
onMounted(loadKeyence)
async function saveKeyence () {
  kMsg.value = ''
  try {
    await api.saveKeyence({ ...keyence })
    await loadKeyence()
    kMsg.value = t('settings.connectionsSaved')
    error.value = ''
  } catch (e) { error.value = errorText(e) }
}

const prefs = computed(() => (store.status && store.status.prefs) || {})
const INC = ['mould_id', 'part_number', 'shot_counter_start']
async function toggleInc (f) {
  const cur = new Set(prefs.value.auto_increment || [])
  if (cur.has(f)) cur.delete(f)
  else cur.add(f)
  await savePrefs({ auto_increment: [...cur] })
}
const recording = computed(() => store.status && ['starting', 'recording', 'stopping', 'verifying'].includes(store.status.state))
</script>

<template>
  <div class="settings">
    <h1>{{ t('settings.title') }}</h1>

    <section class="panel panel-pad">
      <div class="panel-head"><h2>{{ t('settings.connections') }}</h2></div>
      <p class="small muted lead">{{ t('settings.connectionsHint') }}</p>
      <table class="data conn">
        <thead>
          <tr><th></th><th>{{ t('settings.address') }}</th><th>{{ t('settings.user') }}</th><th>{{ t('settings.password') }}</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td class="strong">{{ camName(r.id) }}</td>
            <td><input v-model="r.ip" type="text" spellcheck="false" :aria-label="t('settings.address')" /></td>
            <td><input v-model="r.user" type="text" spellcheck="false" autocomplete="off" :aria-label="t('settings.user')" /></td>
            <td><input v-model="r.password" type="password" autocomplete="new-password" :placeholder="r.password_set ? t('settings.passwordKeep') : ''" :aria-label="t('settings.password')" /></td>
            <td class="testcell">
              <button class="btn sm" @click="test(r)">{{ t('common.test') }}</button>
              <span class="small" :class="tests[r.id] && tests[r.id].ok ? 'oktext' : tests[r.id] && !tests[r.id].busy ? 'err' : 'muted'">{{ testText(r) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="actions">
        <button class="btn primary" :disabled="busy || recording" @click="saveConnections">{{ t('settings.saveConnections') }}</button>
        <span v-if="msg" class="small oktext">{{ msg }}</span>
        <span v-if="error" class="small err">{{ error }}</span>
      </div>
    </section>

    <section class="panel panel-pad">
      <div class="panel-head"><h2>{{ t('cameras.keyenceTitle') }}</h2></div>
      <p class="small muted lead">{{ t('setup.keyenceHint') }}</p>
      <div class="krow">
        <label class="field"><span class="label">{{ t('cameras.keyenceMode') }}</span>
          <select v-model="keyence.mode">
            <option value="off">{{ t('cameras.keyenceModeOff') }}</option>
            <option value="iv3">{{ t('cameras.keyenceModeIv3') }}</option>
          </select>
        </label>
        <label class="field"><span class="label">{{ t('settings.address') }}</span>
          <input v-model="keyence.host" type="text" spellcheck="false" /></label>
        <label class="field"><span class="label">{{ t('cameras.keyencePort') }}</span>
          <input v-model.number="keyence.port" type="number" min="1" max="65535" /></label>
        <label class="field"><span class="label">{{ t('cameras.keyenceTriggerMode') }}</span>
          <select v-model="keyence.trigger">
            <option :value="true">{{ t('cameras.keyenceTriggerOn') }}</option>
            <option :value="false">{{ t('cameras.keyenceTriggerOff') }}</option>
          </select>
        </label>
        <label class="field"><span class="label">{{ t('cameras.keyenceInterval') }} (s)</span>
          <input v-model.number="keyence.trigger_interval_s" type="number" min="0.5" max="300" step="0.5"
                 :disabled="!keyence.trigger" /></label>
        <label class="field"><span class="label">{{ t('cameras.keyenceFtpPort') }}</span>
          <input v-model.number="keyence.ftp_port" type="number" min="1" max="65535" /></label>
      </div>
      <div class="actions">
        <button class="btn primary" :disabled="recording" @click="saveKeyence">{{ t('common.save') }}</button>
        <span v-if="kMsg" class="small oktext">{{ kMsg }}</span>
      </div>
    </section>

    <div class="two">
      <section class="panel panel-pad">
        <div class="panel-head"><h2>{{ t('settings.numbering') }}</h2></div>
        <p class="small muted lead">{{ t('settings.numberingHint') }}</p>
        <label v-for="f in INC" :key="f" class="check">
          <input type="checkbox" :checked="(prefs.auto_increment || []).includes(f)" @change="toggleInc(f)" />
          {{ t('field.' + f) }}
        </label>
      </section>

      <section class="panel panel-pad">
        <div class="panel-head"><h2>{{ t('settings.language') }}</h2></div>
        <div class="segmented" role="group">
          <button :aria-pressed="prefs.language !== 'sl'" @click="savePrefs({ language: 'en' })">English</button>
          <button :aria-pressed="prefs.language === 'sl'" @click="savePrefs({ language: 'sl' })">Slovenščina</button>
        </div>
        <div class="panel-head gap"><h2>{{ t('settings.theme') }}</h2></div>
        <div class="segmented" role="group">
          <button :aria-pressed="prefs.theme !== 'dark'" @click="savePrefs({ theme: 'light' })">{{ t('settings.light') }}</button>
          <button :aria-pressed="prefs.theme === 'dark'" @click="savePrefs({ theme: 'dark' })">{{ t('settings.dark') }}</button>
        </div>
      </section>
    </div>

    <div class="two">
      <section class="panel panel-pad">
        <div class="panel-head"><h2>{{ t('settings.backup') }}</h2></div>
        <p class="small muted lead">{{ t('settings.backupHint') }}</p>
        <div class="backups">
          <a v-for="c in store.config.cameras" :key="c.id" class="btn sm" :class="{ disabled: recording }"
             :href="recording ? null : `/api/cameras/${c.id}/backup`" download>{{ t('settings.download') }}: {{ camName(c.id) }}</a>
        </div>
      </section>

      <section v-if="conn" class="panel panel-pad">
        <div class="panel-head"><h2>{{ t('settings.system') }}</h2></div>
        <table class="kv small">
          <tr><th>{{ t('settings.configFile') }}</th><td class="num">{{ conn.config_file }}</td></tr>
          <tr><th>{{ t('settings.dataDir') }}</th><td class="num">{{ conn.data_dir }}</td></tr>
          <tr><th>{{ t('settings.ffmpeg') }}</th><td class="num">{{ conn.ffmpeg || '\u2013' }}</td></tr>
          <tr v-if="conn.simulate"><th>{{ t('settings.simulation') }}</th><td>{{ t('common.on') }}</td></tr>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: var(--gap); max-width: 1180px; }
h1 { font-size: var(--fs-xl); }
.lead { max-width: 80ch; margin-bottom: 10px; }
.conn td { padding: 6px 10px 6px 0; }
.conn input { min-width: 150px; }
.strong { font-weight: 600; white-space: nowrap; }
.testcell { display: flex; align-items: center; gap: 10px; min-width: 300px; }
.actions { display: flex; align-items: center; gap: 14px; margin-top: 12px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }
.krow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.check { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.check input { width: 16px; height: 16px; }
.gap { margin-top: 16px; }
.backups { display: flex; gap: 8px; flex-wrap: wrap; }
a.btn { text-decoration: none; }
a.btn.disabled { opacity: .5; pointer-events: none; }
table.kv { width: 100%; border-collapse: collapse; }
.kv th { text-align: left; color: var(--muted); font-weight: 500; padding: 5px 12px 5px 0; width: 36%; vertical-align: top; }
.kv td { padding: 5px 0; word-break: break-all; }
.kv tr + tr th, .kv tr + tr td { border-top: 1px solid var(--line); }
.oktext { color: var(--ok); }
.err { color: var(--fault); }
</style>
