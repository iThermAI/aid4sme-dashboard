<script setup>
import { computed } from 'vue'
import { store } from '../store.js'
import { t } from '../i18n.js'
import { timeOfDay } from '../format.js'
import LatticeMark from './brand/LatticeMark.vue'
import AidLogo from './brand/AidLogo.vue'
import ElvezMark from './brand/ElvezMark.vue'

const props = defineProps({ active: Boolean })
const emit = defineEmits(['about'])

const s = computed(() => store.status)
const tabs = ['run', 'sessions', 'cameras', 'settings']
const stateKey = computed(() => {
  if (!s.value) return 'connecting'
  if (s.value.state === 'idle') return s.value.blockers.length ? 'notReady' : 'ready'
  return s.value.state
})
const dotClass = computed(() => {
  if (props.active) return 'rec'
  if (stateKey.value === 'ready') return ''
  if (stateKey.value === 'finished') return ''
  return 'idle'
})
const forecast = computed(() => (s.value && s.value.disk ? s.value.disk.forecast : null))
</script>

<template>
  <header class="header" :class="{ active }">
    <button class="brand" :title="t('nav.about')" @click="emit('about')">
      <span class="mark"><LatticeMark :animated="active" /></span>
      <span class="word"><AidLogo /></span>
      <span class="product">Dashboard</span>
    </button>

    <nav v-if="!active" class="tabs" aria-label="Main">
      <button v-for="tab in tabs" :key="tab" :aria-current="store.view === tab ? 'page' : null"
              @click="store.view = tab">{{ t('nav.' + tab) }}</button>
    </nav>

    <div class="right">
      <span v-if="s && s.simulate" class="badge warn">{{ t('settings.simulation') }}</span>
      <span class="state"><span class="dot" :class="dotClass"></span>{{ t('state.' + stateKey) }}</span>
      <span v-if="s" class="meta num" :title="forecast ? t('common.hoursLeft', { v: forecast.hours_left }) : ''">
        {{ t('common.gbFree', { v: s.disk.free_gb }) }}
      </span>
      <span v-if="s" class="meta num clock">{{ timeOfDay(s.server_time) }}</span>
      <span class="sep" aria-hidden="true"></span>
      <span class="elvez" title="ELVEZ"><ElvezMark /></span>
    </div>
  </header>
  <div class="brandline" :class="{ active }" aria-hidden="true"></div>
</template>

<style scoped>
.header {
  height: var(--header);
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 0 var(--pad);
  background: var(--surface);
  color: var(--ink);
}
.header.active { background: var(--rec-band); color: #fff; }
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  background: none;
  padding: 4px 6px 4px 0;
  cursor: pointer;
  color: inherit;
  border-radius: var(--r-sm);
}
.mark { height: 34px; display: block; }
.word { height: 15px; display: block; color: var(--navy); }
:root[data-theme="dark"] .word, .header.active .word { color: #fff; }
.product {
  font-family: var(--font-read);
  font-weight: 500;
  font-size: 19px;
  letter-spacing: 0.01em;
  color: var(--ink-2);
  padding-left: 10px;
  border-left: 1px solid var(--line-strong);
  line-height: 1;
}
.header.active .product { color: #b9cbe0; border-left-color: rgba(255, 255, 255, .25); }

.tabs { display: flex; gap: 2px; height: 100%; }
.tabs button {
  border: 0;
  background: none;
  height: 100%;
  padding: 0 14px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  position: relative;
}
.tabs button:hover { color: var(--ink); }
.tabs button[aria-current="page"] { color: var(--ink); }
.tabs button[aria-current="page"]::after {
  content: "";
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: var(--primary);
}

.right { margin-left: auto; display: flex; align-items: center; gap: 18px; white-space: nowrap; }
.state { display: inline-flex; align-items: center; gap: 8px; font-weight: 500; }
.meta { color: var(--muted); font-size: var(--fs-sm); }
.header.active .meta { color: #9fb3c8; }
.clock { min-width: 60px; }
.sep { width: 1px; height: 24px; background: var(--line); }
.header.active .sep { background: rgba(255, 255, 255, .2); }
.elvez { height: 22px; display: block; color: var(--ink); }
.header.active .elvez { color: #fff; }

.brandline { height: 2px; background: var(--brand-gradient); }
.brandline.active { height: 0; }

@media (max-width: 1180px) {
  .product { display: none; }
  .meta:not(.clock) { display: none; }
}
</style>
