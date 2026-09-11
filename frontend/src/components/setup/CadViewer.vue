<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Box3, Color, DirectionalLight, HemisphereLight, PerspectiveCamera, Scene, Vector3, WebGLRenderer
} from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { store } from '../../store.js'
import { api } from '../../api.js'
import { t, errorText } from '../../i18n.js'

const host = ref(null)
const fileInput = ref(null)
const error = ref('')
const busy = ref(false)
let renderer = null
let scene = null
let camera = null
let controls = null
let model = null
let resizeObs = null

const render = () => { if (renderer) renderer.render(scene, camera) }

function background () {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? '#122434' : '#e7ecf1'
}

function init () {
  try {
    renderer = new WebGLRenderer({ antialias: true })
  } catch (e) {
    error.value = t('setup.noWebgl')
    return
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  host.value.appendChild(renderer.domElement)
  scene = new Scene()
  scene.background = new Color(background())
  scene.add(new HemisphereLight(0xffffff, 0x8a939b, 2.2))
  const sun = new DirectionalLight(0xffffff, 1.6)
  sun.position.set(3, 5, 4)
  scene.add(sun)
  camera = new PerspectiveCamera(40, 1, 0.001, 1000)
  camera.position.set(1, 1, 1)
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = false          // render on demand only: no idle GPU load
  controls.addEventListener('change', render)
  resizeObs = new ResizeObserver(resize)
  resizeObs.observe(host.value)
  resize()
}

function resize () {
  if (!renderer || !host.value) return
  const w = host.value.clientWidth
  const h = host.value.clientHeight
  renderer.setSize(w, h)
  camera.aspect = w / Math.max(h, 1)
  camera.updateProjectionMatrix()
  render()
}

function disposeModel () {
  if (!model) return
  scene.remove(model)
  model.traverse((o) => {
    if (o.geometry) o.geometry.dispose()
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
    mats.forEach((m) => {
      Object.values(m).forEach((v) => { if (v && v.isTexture) v.dispose() })
      m.dispose()
    })
  })
  model = null
}

function loadModel () {
  if (!renderer) return
  disposeModel()
  render()
  if (!store.draft.cad) return
  busy.value = true
  error.value = ''
  new GLTFLoader().load(`/api/draft/cad?t=${Date.now()}`, (gltf) => {
    model = gltf.scene
    scene.add(model)
    const box = new Box3().setFromObject(model)
    const size = box.getSize(new Vector3()).length() || 1
    const centre = box.getCenter(new Vector3())
    controls.target.copy(centre)
    camera.near = size / 1000
    camera.far = size * 100
    camera.position.copy(centre).add(new Vector3(0.6, 0.45, 0.75).multiplyScalar(size))
    camera.updateProjectionMatrix()
    controls.update()
    busy.value = false
    render()
  }, undefined, () => {
    busy.value = false
    error.value = t('setup.cadError')
  })
}

async function upload (ev) {
  const file = ev.target.files && ev.target.files[0]
  ev.target.value = ''
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    store.draft = await api.uploadCad(file)
  } catch (e) {
    error.value = errorText(e)
    busy.value = false
  }
}

async function remove () {
  try {
    store.draft = await api.removeCad()
  } catch (e) {
    error.value = errorText(e)
  }
}

onMounted(() => {
  init()
  loadModel()
})
// Reload whenever the draft's model changes (upload, preset, removal).
watch(() => store.draft && JSON.stringify([store.draft.cad, store.draft.part_preset]), (now, before) => {
  if (now !== before) { busy.value = false; loadModel() }
})
onBeforeUnmount(() => {
  if (resizeObs) resizeObs.disconnect()
  disposeModel()
  if (controls) controls.dispose()
  if (renderer) {
    renderer.dispose()
    renderer.forceContextLoss()
    renderer.domElement.remove()
  }
  renderer = null
})
</script>

<template>
  <section class="cad">
    <div class="panel-head">
      <h2>{{ t('setup.partModel') }}</h2>
      <template v-if="store.draft.cad">
        <button class="link small" @click="fileInput.click()">{{ t('setup.replace') }}</button>
        <button class="link small" @click="remove">{{ t('setup.remove') }}</button>
      </template>
    </div>
    <div class="stage" :class="{ empty: !store.draft.cad }">
      <div ref="host" class="host"></div>
      <div v-if="!store.draft.cad" class="empty-msg">
        <p class="small muted">{{ t('setup.cadEmpty') }}</p>
        <button class="btn sm" @click="fileInput.click()">{{ t('setup.loadGlb') }}</button>
      </div>
      <p v-if="busy" class="overlay small">{{ t('common.loading') }}</p>
    </div>
    <p v-if="store.draft.cad" class="xs muted file">{{ store.draft.cad.filename }}</p>
    <p v-if="error" class="small err">{{ error }}</p>
    <input ref="fileInput" type="file" accept=".glb,model/gltf-binary" hidden @change="upload" />
  </section>
</template>

<style scoped>
.stage { position: relative; height: 150px; border-radius: var(--r-sm); overflow: hidden; background: var(--surface-3); }
.host { position: absolute; inset: 0; }
.stage.empty .host { display: none; }
.empty-msg { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 12px; text-align: center; }
.overlay { position: absolute; left: 8px; bottom: 8px; background: var(--surface); padding: 2px 8px; border-radius: var(--r-sm); }
.file { margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.err { color: var(--fault); margin-top: 6px; }
</style>
