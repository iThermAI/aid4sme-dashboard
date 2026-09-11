<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { t } from '../../i18n.js'

defineProps({ title: String, wide: Boolean })
const emit = defineEmits(['close'])
const box = ref(null)

function onKey (e) { if (e.key === 'Escape') emit('close') }
onMounted(() => {
  document.addEventListener('keydown', onKey)
  if (box.value) box.value.focus()
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="backdrop" @mousedown.self="emit('close')">
    <div ref="box" class="modal" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
      <header>
        <h2>{{ title }}</h2>
        <button class="btn ghost icon" :aria-label="t('common.close')" @click="emit('close')">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 4l8 8M12 4l-8 8"/></svg>
        </button>
      </header>
      <div class="body"><slot /></div>
      <footer v-if="$slots.footer"><slot name="footer" /></footer>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 12, 20, .55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 24px;
}
.modal {
  width: min(560px, 100%);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-2);
  outline: none;
}
.modal.wide { width: min(880px, 100%); }
header { display: flex; align-items: center; gap: 12px; padding: 14px 16px 10px 20px; }
header h2 { flex: 1; font-size: var(--fs-lg); }
.body { padding: 4px 20px 16px; overflow-y: auto; }
footer { display: flex; justify-content: flex-end; gap: 10px; padding: 12px 20px 16px; border-top: 1px solid var(--line); }
</style>
