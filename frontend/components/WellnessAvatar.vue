<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, defineExpose } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils, type VRM } from '@pixiv/three-vrm'

const props = defineProps<{
  vrmUrl?: string  // default: /avatars/wellness.vrm
  height?: number  // px; default 320
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

// Lip-sync state — driven by parent via setMouthOpen(0..1)
let mouthOpenTarget = 0
let mouthOpenSmoothed = 0

function setMouthOpen(value: number) {
  mouthOpenTarget = Math.max(0, Math.min(1, value))
}

defineExpose({ setMouthOpen })

onMounted(async () => {
  if (!canvasEl.value) return

  const width = canvasEl.value.clientWidth || 320
  const height = props.height ?? 320

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(28, width / height, 0.1, 20)
  camera.position.set(0, 1.4, 1.2)
  camera.lookAt(0, 1.4, 0)

  renderer = new THREE.WebGLRenderer({ canvas: canvasEl.value, alpha: true, antialias: true })
  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

  const ambient = new THREE.AmbientLight(0xffffff, 0.7)
  const dir = new THREE.DirectionalLight(0xffffff, 0.9)
  dir.position.set(1, 2, 2)
  scene.add(ambient, dir)

  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))

  const url = props.vrmUrl ?? '/avatars/wellness.vrm'
  try {
    const gltf = await loader.loadAsync(url)
    vrm = gltf.userData.vrm as VRM
    VRMUtils.removeUnnecessaryVertices(gltf.scene)
    VRMUtils.removeUnnecessaryJoints(gltf.scene)
    // VRM 1.0 spec: model "front" is -Z. Camera sits at +Z, so without
    // this rotation we'd see the back of the head. 180° on Y flips the
    // model to face the camera.
    vrm.scene.rotation.y = Math.PI
    // Break out of T-pose into a relaxed idle stance. VRM rest pose has
    // arms extended outward; rotating the upper-arm Z axis brings them
    // down to the sides. Sign is opposite per side because of the
    // mirrored arm chain.
    const leftUpperArm = vrm.humanoid?.getNormalizedBoneNode('leftUpperArm')
    const rightUpperArm = vrm.humanoid?.getNormalizedBoneNode('rightUpperArm')
    if (leftUpperArm) leftUpperArm.rotation.z = 1.3   // ~75° down
    if (rightUpperArm) rightUpperArm.rotation.z = -1.3
    // Slight forearm bend for a natural standing pose
    const leftLowerArm = vrm.humanoid?.getNormalizedBoneNode('leftLowerArm')
    const rightLowerArm = vrm.humanoid?.getNormalizedBoneNode('rightLowerArm')
    if (leftLowerArm) leftLowerArm.rotation.y = 0.2
    if (rightLowerArm) rightLowerArm.rotation.y = -0.2
    scene.add(vrm.scene)
    status.value = 'ready'
  } catch (e) {
    status.value = 'error'
    errorMsg.value = e instanceof Error ? e.message : String(e)
    return
  }

  clock = new THREE.Clock()
  const animate = () => {
    rafId = requestAnimationFrame(animate)
    const dt = clock!.getDelta()
    const t = clock!.elapsedTime

    if (vrm) {
      // Idle breathing — sine on spine
      const spine = vrm.humanoid?.getNormalizedBoneNode('spine')
      if (spine) spine.rotation.x = Math.sin(t * 1.4) * 0.02

      // Lip sync: smooth toward target, drive 'aa' blendshape
      mouthOpenSmoothed += (mouthOpenTarget - mouthOpenSmoothed) * Math.min(1, dt * 18)
      vrm.expressionManager?.setValue('aa', mouthOpenSmoothed)
      vrm.update(dt)
    }

    renderer!.render(scene!, camera!)
  }
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  renderer?.dispose()
  if (vrm) VRMUtils.deepDispose(vrm.scene)
  scene = null
  camera = null
  vrm = null
})
</script>

<template>
  <div class="wellness-avatar relative" :style="{ height: (props.height ?? 320) + 'px' }">
    <canvas ref="canvasEl" class="w-full h-full block"></canvas>
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
