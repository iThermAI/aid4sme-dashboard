<script setup>
import { store } from '../store.js'
import { t } from '../i18n.js'
import Modal from './ui/Modal.vue'
import AidLogo from './brand/AidLogo.vue'
import ElvezMark from './brand/ElvezMark.vue'
import LatticeMark from './brand/LatticeMark.vue'
import ithermaiMain from '../assets/ithermai-main.png'

const emit = defineEmits(['close'])
</script>

<template>
  <Modal :title="t('about.title')" @close="emit('close')">
    <div class="hero">
      <span class="lattice"><LatticeMark animated /></span>
      <div>
        <p class="name"><span class="aid"><AidLogo /></span> Dashboard</p>
        <p class="muted small">{{ t('about.version', { v: store.config ? store.config.version : '' }) }}</p>
      </div>
    </div>
    <p class="text">{{ t('about.text') }}</p>
    <p class="text">{{ t('about.partners') }}</p>
    <div class="logos">
      <img :src="ithermaiMain" alt="iThermAI" class="ith" />
      <span class="elvez"><ElvezMark /><span class="elvez-word">ELVEZ</span></span>
    </div>
    <p class="funding small">{{ t('about.funding') }}</p>
    <p class="small muted">{{ t('about.license') }}</p>
  </Modal>
</template>

<style scoped>
.hero { display: flex; align-items: center; gap: 16px; margin-bottom: 14px; }
.lattice { height: 72px; display: block; }
.name { display: flex; align-items: center; gap: 10px; font-family: var(--font-read); font-size: 22px; font-weight: 500; }
.aid { height: 18px; display: block; color: var(--ink); }
.text { margin-bottom: 10px; max-width: 64ch; }
.logos { display: flex; align-items: center; gap: 36px; padding: 16px 0; margin: 6px 0 12px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.ith { height: 40px; width: auto; }
:root[data-theme="dark"] .ith { background: #fff; padding: 4px 8px; border-radius: 4px; }
.elvez { display: flex; align-items: center; gap: 8px; height: 30px; color: var(--ink); }
.elvez-word { font-weight: 600; letter-spacing: .14em; font-size: 15px; }
.funding { margin-bottom: 8px; max-width: 70ch; }
</style>
