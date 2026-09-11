<script setup>
import { computed, onMounted, ref } from 'vue'
import { store, loadInitial, startPolling } from './store.js'
import { t } from './i18n.js'
import AppHeader from './components/AppHeader.vue'
import AboutDialog from './components/AboutDialog.vue'
import SetupView from './components/setup/SetupView.vue'
import RecordingView from './components/rec/RecordingView.vue'
import SummaryView from './components/rec/SummaryView.vue'
import SessionsView from './components/SessionsView.vue'
import CamerasView from './components/cameras/CamerasView.vue'
import SettingsView from './components/settings/SettingsView.vue'

const about = ref(false)
const state = computed(() => (store.status ? store.status.state : null))
const active = computed(() => ['starting', 'recording', 'stopping', 'verifying'].includes(state.value))
const ready = computed(() => store.config && store.draft && store.status)

onMounted(() => {
  loadInitial()
  startPolling()
})
</script>

<template>
  <AppHeader :active="active" @about="about = true" />
  <div v-if="store.connectionLost" class="conn notice fault" role="alert">{{ t('conn.offline') }}</div>
  <main v-if="ready" :class="{ flush: active }">
    <RecordingView v-if="active" />
    <SummaryView v-else-if="state === 'finished' && store.view === 'run'" />
    <SessionsView v-else-if="store.view === 'sessions'" />
    <CamerasView v-else-if="store.view === 'cameras'" />
    <SettingsView v-else-if="store.view === 'settings'" />
    <SetupView v-else />
  </main>
  <main v-else class="loading">
    <p class="muted">{{ store.loadError ? t('conn.waiting') + ' ' + store.loadError : t('conn.waiting') }}</p>
  </main>
  <AboutDialog v-if="about" @close="about = false" />
</template>

<style scoped>
main { padding: var(--pad); }
main.flush { padding-top: 0; }
.conn { border-radius: 0; }
.loading { padding: 40px; }
</style>
