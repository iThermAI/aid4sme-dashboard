import { reactive, watch } from 'vue'
import { api } from './api.js'
import { locale } from './i18n.js'

export const store = reactive({
  config: null,
  status: null,
  draft: null,
  connectionLost: false,
  loadError: '',
  view: 'run',
  prefsLoaded: false
})

export async function loadInitial () {
  try {
    store.config = await api.config()
    store.draft = await api.draft()
    store.loadError = ''
  } catch (e) {
    store.loadError = e.message
    setTimeout(loadInitial, 3000)
  }
}

export async function reloadDraft () {
  store.draft = await api.draft()
}

function applyPrefs (prefs) {
  if (!prefs) return
  locale.value = prefs.language || 'en'
  document.documentElement.setAttribute('data-theme', prefs.theme || 'light')
  document.documentElement.setAttribute('lang', prefs.language || 'en')
}

export async function savePrefs (patch) {
  const prefs = await api.prefs(patch)
  if (store.status) store.status.prefs = prefs
  applyPrefs(prefs)
  return prefs
}

export function startPolling () {
  const loop = async () => {
    try {
      const s = await api.status()
      store.status = s
      store.connectionLost = false
      if (!store.prefsLoaded) {
        applyPrefs(s.prefs)
        store.prefsLoaded = true
      }
    } catch (e) {
      store.connectionLost = true
    }
    setTimeout(loop, 1000)
  }
  loop()
}

// Returning to the dashboard (e.g. from a camera's own web page) re-reads camera settings.
export function onReturn (fn) {
  const handler = () => { if (document.visibilityState === 'visible') fn() }
  window.addEventListener('focus', handler)
  document.addEventListener('visibilitychange', handler)
  return () => {
    window.removeEventListener('focus', handler)
    document.removeEventListener('visibilitychange', handler)
  }
}

watch(() => store.status && store.status.prefs, (p) => { if (p && store.prefsLoaded) applyPrefs(p) })
