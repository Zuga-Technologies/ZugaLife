<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, defineExpose } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils, type VRM } from '@pixiv/three-vrm'

const props = defineProps<{
  vrmUrl?: string
  height?: number
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
const status = ref<'loading' | 'ready' | 'error'>('loading')
const errorMsg = ref('')

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let vrm: VRM | null = null
let clock: THREE.Clock | null = null
let rafId = 0
let resizeObs: ResizeObserver | null = null

let mouthOpenTarget = 0
let mouthOpenSmoothed = 0
let mouthMesh: THREE.Object3D | null = null

// Blink schedule — closes the eyes briefly every few seconds. Stored as a
// running cycle so animate() can interpolate without allocating per frame.
let nextBlinkAt = 2 + Math.random() * 3
let blinkPhase = 0

function setMouthOpen(value: number) {
  mouthOpenTarget = Math.max(0, Math.min(1, value))
}

defineExpose({ setMouthOpen })

function fit() {
  if (!renderer || !camera || !canvasEl.value) return
  const w = canvasEl.value.clientWidth || 320
  const h = canvasEl.value.clientHeight || (props.height ?? 420)
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

onMounted(async () => {
  if (!canvasEl.value) return

  const height = props.height ?? 420

  scene = new THREE.Scene()
  // Full-body framing: camera further back, slight downward tilt so feet
  // land near the bottom of the canvas without cropping.
  camera = new THREE.PerspectiveCamera(32, 1, 0.1, 20)
  camera.position.set(0, 1.05, 3.2)
  camera.lookAt(0, 0.95, 0)

  renderer = new THREE.WebGLRenderer({ canvas: canvasEl.value, alpha: true, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(canvasEl.value.clientWidth || 320, height, false)

  // Soft three-point lighting — ambient fill + key from camera-right + rim
  // from behind/above on the opposite side. Gives the model gentle depth
  // without making it look like a video game.
  const ambient = new THREE.AmbientLight(0xfff5e8, 0.55)
  const key = new THREE.DirectionalLight(0xfff1da, 0.85)
  key.position.set(2, 2.5, 2)
  const rim = new THREE.DirectionalLight(0xc9d4ff, 0.45)
  rim.position.set(-2, 3, -1.5)
  scene.add(ambient, key, rim)

  // Floor disc — soft round shadow catcher so the robot doesn't appear to
  // float. Removed below if the garage GLB loads successfully (the garage
  // ships its own floor; keeping both causes z-fighting).
  const floorGeo = new THREE.CircleGeometry(0.9, 48)
  const floorMat = new THREE.MeshBasicMaterial({
    color: 0x000000,
    transparent: true,
    opacity: 0.18,
  })
  const floor = new THREE.Mesh(floorGeo, floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.position.y = 0.001
  scene.add(floor)

  // Cyberpunk garage scene — static GLB loaded around the robot. Failure is
  // non-fatal: the robot still renders against the gradient background.
  const sceneLoader = new GLTFLoader()
  sceneLoader
    .loadAsync('/scenes/cyberpunk-garage.glb')
    .then((gltf) => {
      scene!.remove(floor)
      scene!.add(gltf.scene)
    })
    .catch((e) => {
      console.warn('[WellnessAvatar] garage scene unavailable:', e)
    })

  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))

  const url = props.vrmUrl ?? '/avatars/wellness-robot.vrm'
  try {
    const gltf = await loader.loadAsync(url)
    vrm = gltf.userData.vrm as VRM
    VRMUtils.removeUnnecessaryVertices(gltf.scene)
    VRMUtils.removeUnnecessaryJoints(gltf.scene)
    // No Math.PI flip needed — wellness-robot.vrm was authored facing -Y in
    // Blender, which converts to +Z (toward three.js camera) on glTF Y-up
    // export. The original anime VRM faced -Z and needed the 180° flip; ours
    // doesn't. Leaving this commented as a marker in case a future
    // vrmUrl-prop override loads a -Z-facing VRM and visibly turns its back.
    // vrm.scene.rotation.y = Math.PI

    // Rest pose: drop arms from T-pose binding pose (VRM 1.0 spec) to sides.
    // Sign convention is OPPOSITE of the original anime VRM because that
    // model shipped with arms-down bind; ours ships with proper T-pose bind,
    // and three-vrm's normalized rotation.z flips meaning across the two.
    const leftUpperArm = vrm.humanoid?.getNormalizedBoneNode('leftUpperArm')
    const rightUpperArm = vrm.humanoid?.getNormalizedBoneNode('rightUpperArm')
    if (leftUpperArm) leftUpperArm.rotation.z = -1.3
    if (rightUpperArm) rightUpperArm.rotation.z = 1.3
    const leftLowerArm = vrm.humanoid?.getNormalizedBoneNode('leftLowerArm')
    const rightLowerArm = vrm.humanoid?.getNormalizedBoneNode('rightLowerArm')
    if (leftLowerArm) leftLowerArm.rotation.y = -0.2
    if (rightLowerArm) rightLowerArm.rotation.y = 0.2

    // Find the digital mouth mesh — Vue scales its Y axis from
    // mouthOpenSmoothed each frame so the mouth glyph 'pulses' with TTS audio.
    // Glyph is intentionally bound to the cranium head bone (not jaw) so it
    // stays flush with the visor; the audio-driven scale gives the digital
    // monitor-face the speaking effect.
    mouthMesh = vrm.scene.getObjectByName('mesh_mouth') ?? null
    scene.add(vrm.scene)
    status.value = 'ready'
  } catch (e) {
    status.value = 'error'
    errorMsg.value = e instanceof Error ? e.message : String(e)
    return
  }

  fit()
  resizeObs = new ResizeObserver(fit)
  resizeObs.observe(canvasEl.value)

  clock = new THREE.Clock()
  const animate = () => {
    rafId = requestAnimationFrame(animate)
    const dt = clock!.getDelta()
    const t = clock!.elapsedTime

    if (vrm) {
      const hum = vrm.humanoid
      const spine = hum?.getNormalizedBoneNode('spine')
      const chest = hum?.getNormalizedBoneNode('chest')
      const neck = hum?.getNormalizedBoneNode('neck')
      const head = hum?.getNormalizedBoneNode('head')
      const hips = hum?.getNormalizedBoneNode('hips')
      const lUA = hum?.getNormalizedBoneNode('leftUpperArm')
      const rUA = hum?.getNormalizedBoneNode('rightUpperArm')

      // Breathing — slow sine on chest+spine, ~14 cycles/min.
      const breath = Math.sin(t * 1.4) * 0.018
      if (spine) spine.rotation.x = breath
      if (chest) chest.rotation.x = breath * 0.6

      // Weight shift — slow lateral hip sway over ~6s. Gives her a natural
      // standing presence instead of a stock-still T-pose feel.
      const sway = Math.sin(t * 0.55)
      if (hips) {
        hips.rotation.z = sway * 0.025
        hips.position.x = sway * 0.015
      }

      // Head + neck — subtle counter-sway and a shallower vertical drift so
      // her gaze doesn't lock onto a single point.
      if (neck) neck.rotation.y = -sway * 0.04
      if (head) {
        head.rotation.y = -sway * 0.05
        head.rotation.x = Math.sin(t * 0.9) * 0.025
      }

      // Arm idle — very small inward/outward swing, layered on top of the
      // resting Z rotation set above. Magnitudes are intentionally tiny.
      if (lUA) lUA.rotation.x = Math.sin(t * 0.7) * 0.04
      if (rUA) rUA.rotation.x = Math.sin(t * 0.7 + 0.6) * 0.04

      // Hand idle — subtle wrist rotation + finger-curl analogue. Robot
      // doesn't have finger bones, so the hand mesh itself rotates around
      // the wrist on different axes. Slightly different phase L vs R so the
      // motion doesn't look mechanical-mirrored.
      const lHand = hum?.getNormalizedBoneNode('leftHand')
      const rHand = hum?.getNormalizedBoneNode('rightHand')
      if (lHand) {
        lHand.rotation.x = Math.sin(t * 1.1) * 0.08         // wrist nod
        lHand.rotation.z = Math.sin(t * 0.6 + 0.4) * 0.05   // wrist tilt
      }
      if (rHand) {
        rHand.rotation.x = Math.sin(t * 1.1 + 1.2) * 0.08
        rHand.rotation.z = Math.sin(t * 0.6 + 1.0) * 0.05
      }

      // Blink — every 2-5s, close the eyes for ~140ms. blinkPhase ramps
      // 0→1→0; expressionManager.blink takes that directly.
      if (t >= nextBlinkAt) {
        blinkPhase += dt * 12
        if (blinkPhase >= 2) {
          blinkPhase = 0
          nextBlinkAt = t + 2 + Math.random() * 3
        }
      }
      const blinkVal = blinkPhase < 1 ? blinkPhase : Math.max(0, 2 - blinkPhase)
      vrm.expressionManager?.setValue('blink', blinkVal)

      // Mouth — smooth toward target driven by the analyser in the parent.
      // Robot has no `aa` blendshape; lip-sync drives the jaw bone hinge
      // (range 0..0.5 rad mapped from mouth-open 0..1). The setValue('aa')
      // call is kept as a no-op fallback in case a non-robot VRM is loaded
      // via the vrmUrl prop and that VRM exposes a real `aa` shape.
      mouthOpenSmoothed += (mouthOpenTarget - mouthOpenSmoothed) * Math.min(1, dt * 18)
      // Digital monitor face: scale the mouth glyph's Y axis with audio.
      // 1.0 idle → up to ~4x when speaking. Reads as a pulsing waveform on
      // the visor screen, matching the "digitized" face aesthetic.
      if (mouthMesh) {
        mouthMesh.scale.y = 1 + mouthOpenSmoothed * 3.0
      }
      // Also still drive the jaw bone so the cable_jaw_l SpringBone swings.
      const jaw = hum?.getNormalizedBoneNode('jaw')
      if (jaw) jaw.rotation.x = mouthOpenSmoothed * 0.4
      vrm.expressionManager?.setValue('aa', mouthOpenSmoothed)

      vrm.update(dt)
    }

    renderer!.render(scene!, camera!)
  }
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  resizeObs?.disconnect()
  renderer?.dispose()
  if (vrm) VRMUtils.deepDispose(vrm.scene)
  scene = null
  camera = null
  vrm = null
  mouthMesh = null
})
</script>

<template>
  <div class="wellness-avatar relative" :style="{ height: (props.height ?? 420) + 'px' }">
    <div class="avatar-bg absolute inset-0 pointer-events-none" aria-hidden="true">
      <div class="bg-glow"></div>
    </div>
    <canvas ref="canvasEl" class="relative w-full h-full block"></canvas>
    <div
      v-if="status === 'loading'"
      class="absolute inset-0 flex items-center justify-center text-xs text-txt-muted"
    >
      Loading avatar...
    </div>
    <div
      v-if="status === 'error'"
      class="absolute inset-0 flex items-center justify-center text-xs text-txt-muted px-4 text-center"
    >
      Avatar unavailable. Chat continues without it.
    </div>
  </div>
</template>

<style scoped>
.avatar-bg {
  /* Warm dawn → dusk vertical gradient. Subtle enough not to compete with
     the model, distinct enough that the canvas no longer looks like a
     transparent rectangle floating on the page. */
  background:
    radial-gradient(ellipse at 50% 110%, rgba(168, 85, 247, 0.12), transparent 65%),
    linear-gradient(180deg, #1a1530 0%, #2a1f4a 45%, #3a2a5a 100%);
  border-radius: inherit;
  overflow: hidden;
}
.bg-glow {
  position: absolute;
  left: 50%;
  top: 65%;
  width: 70%;
  height: 60%;
  transform: translate(-50%, -50%);
  background: radial-gradient(ellipse, rgba(255, 200, 150, 0.18), transparent 70%);
  filter: blur(12px);
}
</style>
