<script setup>
import { onBeforeUnmount, onMounted, reactive } from 'vue'
import { store, onReturn } from '../../store.js'
import { api } from '../../api.js'
import { t, errorText } from '../../i18n.js'
import CameraCard from './CameraCard.vue'
import ProfilesPanel from './ProfilesPanel.vue'

const info = reactive({})
const loading = reactive({})
const errors = reactive({})

async function read (id) {
  if (loading[id]) return
  loading[id] = true
  try {
    info[id] = await api.camera(id)
    errors[id] = ''
  } catch (e) {
    errors[id] = errorText(e)
  } finally {
    loading[id] = false
  }
}
function readAll () { store.config.cameras.forEach((c) => read(c.id)) }

let off = null
onMounted(() => {
  readAll()
  off = onReturn(readAll)     // values may have been changed in the camera's own web page
})
onBeforeUnmount(() => { if (off) off() })
</script>

<template>
  <div class="cams">
    <div class="top">
      <h1>{{ t('cameras.title') }}</h1>
      <p class="small muted">{{ t('cameras.autoRefresh') }}</p>
      <button class="btn" @click="readAll">{{ t('cameras.refreshAll') }}</button>
    </div>
    <ProfilesPanel @changed="readAll" />
    <div class="grid">
      <CameraCard v-for="c in store.config.cameras" :id="c.id" :key="c.id" :info="info[c.id] || null"
                  :loading="!!loading[c.id]" :error="errors[c.id] || ''" @refresh="read(c.id)" />
    </div>
  </div>
</template>

<style scoped>
.cams { display: flex; flex-direction: column; gap: var(--gap); }
.top { display: flex; align-items: center; gap: 16px; }
.top h1 { font-size: var(--fs-xl); }
.top p { flex: 1; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); align-items: start; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
</style>
