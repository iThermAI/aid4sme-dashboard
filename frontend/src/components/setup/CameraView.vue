<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { t, streamLabel } from '../../i18n.js'
import { num } from '../../format.js'

const props = defineProps({
  stream: { type: Object, required: true },          // { name, kind, camera, width, height }
  regions: { type: Array, default: () => [] },       // entries from the draft
  interval: { type: Number, default: 1000 },
  matrixInterval: { type: Number, default: 2000 },
  large: { type: Boolean, default: false }
})
const emit = defineEmits(['regions', 'expand', 'shrink'])

const COLORS = ['#17AAFE', '#FFB020', '#3DDC97', '#FF6FB5', '#A78BFA', '#FF7A59']
const HANDLE_PX = 10
const MAX_ZOOM = 8

const isThermal = computed(() => props.stream.kind === 'thermal')
const aspect = computed(() => props.stream.width / props.stream.height)
const color = (i) => COLORS[i % COLORS.length]

// ---- live image ----------------------------------------------------------
const src = ref('')
const failure = ref('')
let timer = null
let mtimer = null
let alive = true

async function tick () {
  if (!alive) return
  if (document.hidden) { timer = setTimeout(tick, 1500); return }
  try {
    const res = await fetch(`/api/preview/${props.stream.name}?t=${Date.now()}`)
    if (!res.ok) {
      let msg = `HTTP ${res.status}`
      try { msg = (await res.json()).detail || msg } catch (e) { /* not JSON */ }
      throw new Error(msg)
    }
    const url = URL.createObjectURL(await res.blob())
    const old = src.value
    src.value = url
    if (old) setTimeout(() => URL.revokeObjectURL(old), 3000)
    failure.value = ''
    timer = setTimeout(tick, props.interval)
  } catch (e) {
    failure.value = e.message
    timer = setTimeout(tick, 3000)
  }
}

// ---- radiometric matrix (thermal views only) ------------------------------
const matrix = ref(null)
async function mtick () {
  if (!alive || !isThermal.value) return
  if (document.hidden) { mtimer = setTimeout(mtick, 2000); return }
  try {
    const res = await fetch(`/api/thermal/${props.stream.camera}?t=${Date.now()}`)
    if (res.ok) {
      const w = Number(res.headers.get('X-Width'))
      const h = Number(res.headers.get('X-Height'))
      const buf = await res.arrayBuffer()
      if (w * h * 4 === buf.byteLength) matrix.value = { w, h, data: new Float32Array(buf) }
    }
  } catch (e) { /* keep last matrix */ }
  mtimer = setTimeout(mtick, props.matrixInterval)
}

onMounted(() => { tick(); mtick() })
onBeforeUnmount(() => {
  alive = false
  clearTimeout(timer)
  clearTimeout(mtimer)
  clearTimeout(saveTimer)
  if (src.value) URL.revokeObjectURL(src.value)
})

// ---- regions (local working copy, saved with a short debounce) -------------
const local = ref([])
const selected = ref(null)
const drag = ref(null)
let dirty = false
let saveTimer = null

function fromProps () {
  local.value = (props.regions || []).map((r) => ({ id: r.id, name: r.name, ...r.normalized }))
  if (selected.value && !local.value.some((r) => r.id === selected.value)) selected.value = null
}
watch(() => props.regions, () => { if (!drag.value && !dirty) fromProps() }, { deep: true, immediate: true })

function commit () {
  dirty = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('regions', local.value.map((r) => ({ ...r })))
    dirty = false
  }, 250)
}
const selRegion = computed(() => local.value.find((r) => r.id === selected.value) || null)
function removeSelected () {
  if (!selected.value) return
  local.value = local.value.filter((r) => r.id !== selected.value)
  selected.value = null
  commit()
}
function pxSize (r) {
  return `${Math.round(r.w * props.stream.width)} × ${Math.round(r.h * props.stream.height)} px`
}

// ---- view (zoom / pan). The view never changes a region. --------------------
const view = reactive({ s: 1, vx: 0, vy: 0 })
const vw = computed(() => 1 / view.s)
const clamp = (v, a, b) => Math.min(Math.max(v, a), b)
function clampView () {
  view.vx = clamp(view.vx, 0, 1 - vw.value)
  view.vy = clamp(view.vy, 0, 1 - vw.value)
}
function zoomAt (fx, fy, factor) {
  const cx = view.vx + fx * vw.value
  const cy = view.vy + fy * vw.value
  view.s = clamp(view.s * factor, 1, MAX_ZOOM)
  view.vx = cx - fx * vw.value
  view.vy = cy - fy * vw.value
  clampView()
}
function fit () { view.s = 1; view.vx = 0; view.vy = 0 }

const imgStyle = computed(() => ({
  left: `${-view.vx * view.s * 100}%`, top: `${-view.vy * view.s * 100}%`,
  width: `${view.s * 100}%`, height: `${view.s * 100}%`
}))
const pct = (x, y) => ({ left: `${(x - view.vx) / vw.value * 100}%`, top: `${(y - view.vy) / vw.value * 100}%` })

// ---- pointer interaction -------------------------------------------------------
const frame = ref(null)
const mode = ref('pan')          // 'pan' or 'draw'
const cursor = ref('grab')
const hoverTemp = ref(null)

function frac (e) {
  const r = frame.value.getBoundingClientRect()
  return { fx: clamp((e.clientX - r.left) / r.width, 0, 1), fy: clamp((e.clientY - r.top) / r.height, 0, 1), W: r.width, H: r.height }
}
const toContent = (f) => ({ x: view.vx + f.fx * vw.value, y: view.vy + f.fy * vw.value })

function handles (r) {
  return [['nw', r.x, r.y], ['n', r.x + r.w / 2, r.y], ['ne', r.x + r.w, r.y], ['e', r.x + r.w, r.y + r.h / 2],
    ['se', r.x + r.w, r.y + r.h], ['s', r.x + r.w / 2, r.y + r.h], ['sw', r.x, r.y + r.h], ['w', r.x, r.y + r.h / 2]]
}
const CURSORS = { nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize' }

function hit (f) {
  const p = toContent(f)
  if (selRegion.value) {
    for (const [h, hx, hy] of handles(selRegion.value)) {
      const sx = (hx - view.vx) / vw.value * f.W
      const sy = (hy - view.vy) / vw.value * f.H
      if (Math.abs(sx - f.fx * f.W) <= HANDLE_PX && Math.abs(sy - f.fy * f.H) <= HANDLE_PX) {
        return { type: 'resize', id: selRegion.value.id, handle: h }
      }
    }
  }
  for (let i = local.value.length - 1; i >= 0; i--) {
    const r = local.value[i]
    if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) return { type: 'move', id: r.id }
  }
  return { type: 'pan' }
}

function down (e) {
  if (e.button !== 0 && e.button !== 1) return
  frame.value.focus({ preventScroll: true })
  frame.value.setPointerCapture(e.pointerId)
  const f = frac(e)
  const p = toContent(f)
  hoverTemp.value = null
  if (e.button === 1) {
    drag.value = { type: 'pan', f0: f, v0: { vx: view.vx, vy: view.vy } }
    return
  }
  if (mode.value === 'draw') {
    const id = 'r' + Date.now().toString(36)
    local.value.push({ id, name: `${t('view.region')} ${local.value.length + 1}`, x: p.x, y: p.y, w: 0, h: 0 })
    selected.value = id
    drag.value = { type: 'resize', id, handle: 'se', r0: { x: p.x, y: p.y, w: 0, h: 0 }, created: true, moved: false }
    return
  }
  const h = hit(f)
  if (h.type === 'pan') {
    selected.value = null
    drag.value = { type: 'pan', f0: f, v0: { vx: view.vx, vy: view.vy } }
    cursor.value = 'grabbing'
  } else {
    selected.value = h.id
    const r = local.value.find((x) => x.id === h.id)
    drag.value = { ...h, p0: p, r0: { ...r }, moved: false }
  }
}

function move (e) {
  const f = frac(e)
  const d = drag.value
  if (!d) { hover(f); return }
  if (d.type === 'pan') {
    view.vx = d.v0.vx - (f.fx - d.f0.fx) * vw.value
    view.vy = d.v0.vy - (f.fy - d.f0.fy) * vw.value
    clampView()
    return
  }
  const p = toContent(f)
  const r = local.value.find((x) => x.id === d.id)
  if (!r) return
  if (d.type === 'move') {
    r.x = clamp(d.r0.x + p.x - d.p0.x, 0, 1 - r.w)
    r.y = clamp(d.r0.y + p.y - d.p0.y, 0, 1 - r.h)
  } else {
    let l = d.r0.x
    let rt = d.r0.x + d.r0.w
    let tp = d.r0.y
    let bt = d.r0.y + d.r0.h
    const px = clamp(p.x, 0, 1)
    const py = clamp(p.y, 0, 1)
    if (d.handle.includes('w')) l = px
    if (d.handle.includes('e')) rt = px
    if (d.handle.includes('n')) tp = py
    if (d.handle.includes('s')) bt = py
    r.x = Math.min(l, rt); r.w = Math.abs(rt - l)
    r.y = Math.min(tp, bt); r.h = Math.abs(bt - tp)
  }
  d.moved = true
}

function up () {
  const d = drag.value
  drag.value = null
  if (!d) return
  cursor.value = mode.value === 'draw' ? 'crosshair' : 'grab'
  if (d.type === 'pan') return
  const r = local.value.find((x) => x.id === d.id)
  if (d.created) {
    mode.value = 'pan'
    if (!r || r.w < 0.01 || r.h < 0.01) {
      local.value = local.value.filter((x) => x.id !== d.id)
      selected.value = null
      return
    }
  }
  if (d.moved) commit()
}

function hover (f) {
  if (mode.value === 'draw') cursor.value = 'crosshair'
  else {
    const h = hit(f)
    cursor.value = h.type === 'resize' ? CURSORS[h.handle] : h.type === 'move' ? 'move' : 'grab'
  }
  const m = matrix.value
  if (m) {
    const p = toContent(f)
    const i = clamp(Math.floor(p.x * m.w), 0, m.w - 1)
    const j = clamp(Math.floor(p.y * m.h), 0, m.h - 1)
    hoverTemp.value = { v: m.data[j * m.w + i], left: `${f.fx * 100}%`, top: `${f.fy * 100}%` }
  }
}

function wheel (e) {
  const f = frac(e)
  zoomAt(f.fx, f.fy, e.deltaY < 0 ? 1.25 : 0.8)
}
function dblclick (e) {
  if (hit(frac(e)).type !== 'pan') return
  if (view.s > 1.01) fit()
  else { const f = frac(e); zoomAt(f.fx, f.fy, 2.5) }
}

function key (e) {
  if (e.target !== frame.value) return
  const r = selRegion.value
  const step = e.shiftKey ? 10 : 1
  const nudge = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key]
  if (nudge && r) {
    e.preventDefault()
    r.x = clamp(r.x + nudge[0] * step / props.stream.width, 0, 1 - r.w)
    r.y = clamp(r.y + nudge[1] * step / props.stream.height, 0, 1 - r.h)
    commit()
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && r) {
    e.preventDefault()
    removeSelected()
  } else if (e.key === 'Escape') {
    mode.value = 'pan'
    selected.value = null
  } else if (e.key === '+' || e.key === '=') {
    zoomAt(0.5, 0.5, 1.25)
  } else if (e.key === '-') {
    zoomAt(0.5, 0.5, 0.8)
  } else if (e.key === '0') {
    fit()
  }
}

function startDraw () {
  mode.value = mode.value === 'draw' ? 'pan' : 'draw'
  cursor.value = mode.value === 'draw' ? 'crosshair' : 'grab'
  frame.value.focus({ preventScroll: true })
}

// ---- derived display ------------------------------------------------------------
const shadePath = computed(() => 'M0 0H1V1H0Z ' + local.value.map((r) => `M${r.x} ${r.y}h${r.w}v${r.h}h${-r.w}Z`).join(' '))

const stats = computed(() => {
  const m = matrix.value
  const out = {}
  if (!m) return out
  for (const r of local.value) {
    const x0 = clamp(Math.floor(r.x * m.w), 0, m.w - 1)
    const x1 = clamp(Math.ceil((r.x + r.w) * m.w), x0 + 1, m.w)
    const y0 = clamp(Math.floor(r.y * m.h), 0, m.h - 1)
    const y1 = clamp(Math.ceil((r.y + r.h) * m.h), y0 + 1, m.h)
    let mn = Infinity
    let mx = -Infinity
    let sum = 0
    let n = 0
    for (let j = y0; j < y1; j++) {
      for (let i = x0; i < x1; i++) {
        const v = m.data[j * m.w + i]
        if (v < mn) mn = v
        if (v > mx) mx = v
        sum += v
        n++
      }
    }
    out[r.id] = { min: num(mn, 1), max: num(mx, 1), mean: num(sum / n, 1) }
  }
  return out
})

const frameStyle = computed(() => {
  const s = { aspectRatio: `${props.stream.width} / ${props.stream.height}`, cursor: cursor.value }
  if (props.large) s.width = `min(100%, calc((100vh - 190px) * ${aspect.value.toFixed(4)}))`
  return s
})
</script>

<template>
  <figure class="cv" :class="{ large }" :style="large ? null : { flexGrow: aspect }">
    <figcaption>
      <span class="title">{{ streamLabel(stream.name) }}</span>
      <template v-if="selRegion">
        <span class="swatch" :style="{ background: color(local.indexOf(selRegion)) }"></span>
        <input v-model="selRegion.name" class="rname" maxlength="40" :aria-label="t('view.regionName')" @input="commit" @keydown.stop />
        <span v-if="stats[selRegion.id]" class="small num tstats" :title="t('view.stats', stats[selRegion.id])">
          {{ stats[selRegion.id].min }}–{{ stats[selRegion.id].max }} °C
        </span>
        <span v-else class="small muted num">{{ pxSize(selRegion) }}</span>
        <button class="btn ghost icon sm" :title="t('view.deleteRegion')" :aria-label="t('view.deleteRegion')" @click="removeSelected">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5"/></svg>
        </button>
      </template>
      <span v-else class="small muted num meta">
        {{ stream.width }} × {{ stream.height }}<template v-if="local.length">, {{ local.length }} {{ t('view.regions') }}</template>
      </span>
    </figcaption>

    <div ref="frame" class="frame" tabindex="0" :style="frameStyle"
         @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up"
         @pointerleave="hoverTemp = null" @wheel.prevent="wheel" @dblclick="dblclick" @keydown="key">
      <img v-if="src" :src="src" alt="" draggable="false" :style="imgStyle" :class="{ stale: failure }" />
      <p v-if="failure" class="msg small">{{ failure }}</p>
      <p v-else-if="!src" class="msg small">{{ t('view.waiting') }}</p>

      <svg class="shapes" :viewBox="`${view.vx} ${view.vy} ${vw} ${vw}`" preserveAspectRatio="none" aria-hidden="true">
        <path v-if="local.length" class="shade" fill-rule="evenodd" :d="shadePath" />
        <rect v-for="(r, i) in local" :key="r.id" :x="r.x" :y="r.y" :width="r.w" :height="r.h"
              :stroke="color(i)" :class="{ sel: r.id === selected }" fill="none" vector-effect="non-scaling-stroke" />
      </svg>

      <div v-for="(r, i) in local" :key="'label-' + r.id" class="rlabel" :style="{ ...pct(r.x, r.y), background: color(i) }">
        {{ r.name }}<template v-if="stats[r.id]">&ensp;{{ stats[r.id].max }}&thinsp;°C</template>
      </div>
      <template v-if="selRegion">
        <span v-for="h in handles(selRegion)" :key="h[0]" class="handle" :style="pct(h[1], h[2])"></span>
      </template>

      <div v-if="hoverTemp" class="temp num" :style="{ left: hoverTemp.left, top: hoverTemp.top }">{{ num(hoverTemp.v, 1) }} °C</div>
      <div v-if="view.s > 1.01" class="minimap" aria-hidden="true">
        <span :style="{ left: view.vx * 100 + '%', top: view.vy * 100 + '%', width: vw * 100 + '%', height: vw * 100 + '%' }"></span>
      </div>
      <div v-if="mode === 'draw'" class="drawhint small">{{ t('view.drawHint') }}</div>

      <div class="tools" @pointerdown.stop @dblclick.stop @wheel.stop>
        <button class="tool add" :class="{ on: mode === 'draw' }" :aria-pressed="mode === 'draw'" :title="t('view.addRegion')" @click="startDraw">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2.5" y="2.5" width="11" height="11" rx="1" stroke-dasharray="2 1.6"/><path d="M8 5.5v5M5.5 8h5"/></svg>
          <span>{{ t('view.addRegion') }}</span>
        </button>
        <span class="tsep"></span>
        <button class="tool" :title="t('view.zoomOut')" :aria-label="t('view.zoomOut')" :disabled="view.s <= 1" @click="zoomAt(.5, .5, .8)">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 8h8"/></svg>
        </button>
        <span class="zoom num">{{ Math.round(view.s * 100) }}%</span>
        <button class="tool" :title="t('view.zoomIn')" :aria-label="t('view.zoomIn')" :disabled="view.s >= 8" @click="zoomAt(.5, .5, 1.25)">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 8h8M8 4v8"/></svg>
        </button>
        <button class="tool" :title="t('view.fit')" :aria-label="t('view.fit')" :disabled="view.s <= 1" @click="fit">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"/></svg>
        </button>
        <span class="tsep"></span>
        <button v-if="!large" class="tool" :title="t('view.expand')" :aria-label="t('view.expand')" @click="emit('expand')">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9.5 2.5h4v4M13.5 2.5L9 7M6.5 13.5h-4v-4M2.5 13.5L7 9"/></svg>
        </button>
        <button v-else class="tool" :title="t('view.shrink')" :aria-label="t('view.shrink')" @click="emit('shrink')">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13.5 6.5h-4v-4M9.5 6.5L14 2M2.5 9.5h4v4M6.5 9.5L2 14"/></svg>
        </button>
      </div>
    </div>
  </figure>
</template>

<style scoped>
.cv { margin: 0; flex-basis: 0; flex-shrink: 1; min-width: 0; }
.cv.large { width: 100%; }
figcaption {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  overflow: hidden;
  white-space: nowrap;
}
.title { font-weight: 600; }
.meta { overflow: hidden; text-overflow: ellipsis; }
.swatch { width: 10px; height: 10px; border-radius: 2px; flex: 0 0 auto; }
.rname { width: 112px; min-height: 26px; padding: 2px 8px; font-size: var(--fs-sm); }

.frame {
  position: relative;
  width: 100%;
  margin: 0 auto;
  background: var(--video-bg);
  border-radius: var(--r-md);
  overflow: hidden;
  touch-action: none;
  user-select: none;
  outline-offset: 2px;
}
img { position: absolute; max-width: none; object-fit: fill; pointer-events: none; }
img.stale { opacity: .35; }
.msg { position: absolute; left: 12px; right: 12px; bottom: 12px; color: #fff; background: rgba(9, 29, 45, .8); padding: 6px 10px; border-radius: var(--r-sm); }

.shapes { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.shade { fill: rgba(5, 12, 18, .38); }
.shapes rect { stroke-width: 1.5; }
.shapes rect.sel { stroke-width: 2.5; }

.rlabel {
  position: absolute;
  transform: translateY(calc(-100% - 2px));
  padding: 1px 6px;
  border-radius: 3px 3px 3px 0;
  color: #081521;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
}
.handle {
  position: absolute;
  width: 9px;
  height: 9px;
  transform: translate(-50%, -50%);
  background: #fff;
  border: 1.5px solid #0b74d3;
  border-radius: 2px;
  pointer-events: none;
}
.tstats { font-weight: 600; color: var(--ink); }
.temp {
  position: absolute;
  transform: translate(12px, -130%);
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(9, 29, 45, .9);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  pointer-events: none;
  white-space: nowrap;
}
.minimap {
  position: absolute;
  left: 10px;
  bottom: 10px;
  width: 18%;
  aspect-ratio: inherit;
  border: 1px solid rgba(255, 255, 255, .6);
  background: rgba(9, 29, 45, .45);
  border-radius: 3px;
  pointer-events: none;
}
.minimap span { position: absolute; border: 1.5px solid #17aafe; background: rgba(23, 170, 254, .15); }
.drawhint {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  padding: 4px 12px;
  border-radius: 999px;
  background: #0b74d3;
  color: #fff;
  pointer-events: none;
}

.tools {
  position: absolute;
  right: 8px;
  top: 8px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: var(--r-md);
  background: rgba(9, 29, 45, .78);
  color: #e6eef5;
  cursor: default;
  opacity: .6;
  transition: opacity .15s;
}
.frame:hover .tools, .frame:focus-within .tools { opacity: 1; }
.tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  min-width: 28px;
  padding: 0 7px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
}
.tool svg { width: 15px; height: 15px; }
.tool:hover:not(:disabled) { background: rgba(255, 255, 255, .14); }
.tool:disabled { opacity: .35; cursor: default; }
.tool.on { background: #0b74d3; color: #fff; }
.tsep { width: 1px; height: 18px; background: rgba(255, 255, 255, .2); margin: 0 3px; }
.zoom { font-size: 12px; min-width: 40px; text-align: center; }

@media (max-width: 1500px) {
  .cv:not(.large) .tool.add span { display: none; }
}
</style>
