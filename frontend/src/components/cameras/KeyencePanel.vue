<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { store, onReturn } from '../../store.js'
import { api } from '../../api.js'
import { t, errorText } from '../../i18n.js'

const info = ref(null)
const busy = ref(false)
const message = ref('')
const ok = ref(true)
const shot = ref('')
let off = null
let timer = null

const mode = computed(() => (info.value && info.value.mode) || 'off')

async function load () {
  try {
    info.value = await api.keyence()
  } catch (e) { message.value = errorText(e); ok.value = false }
}

async function picture () {
  // Fetching the live view also starts the camera triggering in the background.
  try {
    const res = await fetch(`/api/preview/keyence?t=${Date.now()}`)
    if (!res.ok) return
    const url = URL.createObjectURL(await res.blob())
    const old = shot.value
    shot.value = url
    if (old) setTimeout(() => URL.revokeObjectURL(old), 2000)
  } catch (e) { /* keep the previous picture */ }
}

async function trigger () {
  busy.value = true
  message.value = ''
  try {
    const r = await api.keyenceTrigger()
    ok.value = r.ok
    message.value = r.ok ? t('cameras.keyenceTriggered', { v: r.trigger_no || '\u2013' }) : t('cameras.keyenceNoPicture')
    await picture()
    await load()
  } catch (e) {
    ok.value = false
    message.value = errorText(e)
  } finally { busy.value = false }
}

onMounted(() => {
  load()
  picture()
  timer = setInterval(() => { load(); picture() }, 4000)
  off = onReturn(load)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  if (off) off()
  if (shot.value) URL.revokeObjectURL(shot.value)
})
</script>

<template>
  <section class="panel panel-pad keyence">
    <div class="panel-head">
      <h2>{{ t('cameras.keyenceTitle') }}</h2>
      <span v-if="info" class="badge" :class="mode !== 'iv3' ? '' : info.reachable === false ? 'fault' : 'ok'">
        {{ mode !== 'iv3' ? t('setup.keyenceNone') : info.reachable === false ? t('setup.offline') : t('setup.online') }}
      </span>
      <span v-if="info && info.host" class="muted small num">{{ info.host }}</span>
      <button class="btn sm" :disabled="busy || mode !== 'iv3'" @click="trigger">
        {{ busy ? t('common.loading') : t('cameras.keyenceTrigger') }}
      </button>
      <button class="link small" @click="store.view = 'settings'">{{ t('nav.settings') }}</button>
    </div>

    <div v-if="mode === 'iv3'" class="body">
      <div class="shot">
        <img v-if="shot" :src="shot" alt="" />
        <p v-else class="small muted wait">{{ t('setup.keyenceWaiting') }}</p>
      </div>
      <table class="kv small">
        <tr><th>{{ t('cameras.keyenceTriggerMode') }}</th>
          <td>{{ info.trigger_enabled === false || info.trigger === false ? t('cameras.keyenceTriggerOff') : t('cameras.keyenceTriggerOn') }}</td></tr>
        <tr v-if="info.trigger !== false"><th>{{ t('cameras.keyenceInterval') }}</th><td class="num">{{ info.trigger_interval_s }} s</td></tr>
        <tr><th>{{ t('cameras.keyenceFtpPort') }}</th><td class="num">{{ info.ftp_port }}</td></tr>
        <tr v-if="info.last_image_age_s !== undefined">
          <th>{{ t('cameras.keyenceLast') }}</th><td class="num">{{ t('cameras.keyenceAge', { v: info.last_image_age_s }) }}</td>
        </tr>
        <tr v-if="info.trigger_no"><th>Trigger no.</th><td class="num">{{ info.trigger_no }}</td></tr>
        <tr v-for="(v, k) in (info.result || {})" :key="k"><th>{{ k }}</th><td class="num">{{ v }}</td></tr>
      </table>
    </div>
    <p v-if="info && info.last_error" class="small warntext">{{ t('cameras.keyenceRefused', { v: info.last_error }) }}</p>
    <p v-if="message" class="small" :class="ok ? 'oktext' : 'err'">{{ message }}</p>
  </section>
</template>

<style scoped>
.body { display: flex; gap: 16px; align-items: flex-start; }
.shot { flex: 0 0 46%; background: var(--video-bg); border-radius: var(--r-md); overflow: hidden; min-height: 140px; display: grid; place-items: center; }
.shot img { width: 100%; display: block; }
.wait { color: #b9cbe0; }
table.kv { flex: 1 1 auto; border-collapse: collapse; }
.kv th { text-align: left; color: var(--muted); font-weight: 500; padding: 4px 12px 4px 0; width: 55%; }
.kv td { padding: 4px 0; }
.kv tr + tr th, .kv tr + tr td { border-top: 1px solid var(--line); }
.oktext { color: var(--ok); margin-top: 8px; }
.warntext { color: var(--warn-ink); margin-top: 8px; }
.err { color: var(--fault); margin-top: 8px; }
</style>
