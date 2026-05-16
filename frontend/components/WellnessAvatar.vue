<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, defineExpose } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils, type VRM } from '@pixiv/three-vrm'

export type AvatarMood = 'neutral' | 'happy' | 'sad' | 'angry' | 'surprised' | 'relaxed'

const props = withDefaults(defineProps<{
  vrmUrl?: string
  height?: number
  mood?: AvatarMood
  moodIntensity?: number
}>(), {
  mood: 'neutral',
  moodIntensity: 0.0,
})

// Per-mood expression vocabulary for the wellness robot. Each entry is the
// target the animate() loop interpolates toward — visor emission color +
// strength, idle-loop multipliers, and a small additive head/spine offset.
// Defined here (not in a character template yet) because we're hardcoding the
// robot first; the character abstraction lands after #1/2/4/5.
interface MoodTarget {
  visor: { r: number; g: number; b: number; strength: number }
  breathRate: number
  swayRate: number
  headTiltX: number
  spineTiltX: number
}
const MOOD_TARGETS: Record<AvatarMood, MoodTarget> = {
  // Default visor color from the VRM (.23, .60, .008) is a warm yellow-green.
  neutral:   { visor: { r: 0.23, g: 0.60, b: 0.008, strength: 1.0 }, breathRate: 1.0, swayRate: 1.0, headTiltX:  0.00, spineTiltX:  0.00 },
  happy:     { visor: { r: 0.95, g: 0.75, b: 0.30,  strength: 1.6 }, breathRate: 1.25, swayRate: 1.20, headTiltX: -0.05, spineTiltX: -0.02 },
  sad:       { visor: { r: 0.12, g: 0.20, b: 0.55,  strength: 0.5 }, breathRate: 0.70, swayRate: 0.70, headTiltX:  0.18, spineTiltX:  0.06 },
  angry:     { visor: { r: 0.95, g: 0.10, b: 0.08,  strength: 1.8 }, breathRate: 1.40, swayRate: 1.30, headTiltX:  0.06, spineTiltX:  0.03 },
  surprised: { visor: { r: 0.80, g: 0.85, b: 0.95,  strength: 1.7 }, breathRate: 1.30, swayRate: 0.90, headTiltX: -0.10, spineTiltX: -0.04 },
  relaxed:   { visor: { r: 0.40, g: 0.85, b: 0.60,  strength: 0.9 }, breathRate: 0.80, swayRate: 0.85, headTiltX:  0.03, spineTiltX:  0.00 },
}

// Smoothed mood state — eased toward target each frame so transitions look
// like the bot is reacting, not snapping. ~1.5s to settle at dt*4.
const moodSmoothed = {
  r: MOOD_TARGETS.neutral.visor.r,
  g: MOOD_TARGETS.neutral.visor.g,
  b: MOOD_TARGETS.neutral.visor.b,
  strength: 1.0,
  breathRate: 1.0,
  swayRate: 1.0,
  headTiltX: 0.0,
  spineTiltX: 0.0,
}

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
let mouthMesh: THREE.SkinnedMesh | null = null
let mouthOpenMorphIndex = -1
// Visor material — its emissive color is driven by mood. Captured once
// during VRM load by name (mat_visor_static) to avoid hot-path lookups.
let visorMaterial: THREE.MeshStandardMaterial | THREE.MeshBasicMaterial | null = null
const visorBaseEmissive = new THREE.Color()
let visorBaseEmissiveIntensity = 1.0

// Eye meshes — captured during VRM load so the animate() loop can scale
// each eye independently for the Star Wars droid "lens zoom" effect. Each
// eye has slightly offset sine-driven scale on Z (depth = how far the iris
// pushes out) and Y (height = squint/widen). Phases differ left vs right
// so the eyes don't move in sync.
let eyeL: THREE.Object3D | null = null
let eyeR: THREE.Object3D | null = null
const eyeBaseScale = { L: new THREE.Vector3(1,1,1), R: new THREE.Vector3(1,1,1) }
// Photoreceptor material — captured during VRM load. The cyan emission
// strength is driven by the audio amplitude each frame so the eyes light
// up while talking and go dark while silent (R2-D2 vibe).
let photoMat: (THREE.Material & { emissiveIntensity?: number; emissive?: THREE.Color }) | null = null
let photoBaseEmissiveIntensity = 0

// Blink schedule — closes the eyes briefly every few seconds. Stored as a
// running cycle so animate() can interpolate without allocating per frame.
let nextBlinkAt = 2 + Math.random() * 3
let blinkPhase = 0

function setMouthOpen(value: number) {
  // Defensive: NaN/Infinity from a bad audio analyser would propagate
  // into mouthOpenSmoothed and make scale.y NaN — invisible mesh.
  if (!isFinite(value)) value = 0
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

  // AAA stylized lighting — low ambient + warm key + strong cool rim from
  // behind. The hard rim highlight is what reads as "video-game render" on a
  // cel-shaded MToon model. Bounce light from below picks up the floor and
  // softens the underside without flattening contrast.
  // Neutral white lighting — cyan rim was tinting acid-lime body to lavender.
  // Now: neutral warm-ish ambient + warm key + neutral white rim (still
  // bright for the AAA cel feel, just doesn't color-shift the body).
  const ambient = new THREE.AmbientLight(0xffffff, 0.55)
  const key = new THREE.DirectionalLight(0xfff1da, 1.1)
  key.position.set(2.4, 2.8, 2.2)
  const rim = new THREE.DirectionalLight(0xffffff, 1.4)
  rim.position.set(-1.5, 3.0, -2.5)
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

  // Cache-bust query string forces SW + CF + browser to fetch the latest VRM
  // whenever its bytes change (avatar revisions). The version tag bumps with
  // each material/geometry edit on the asset.
  const url = props.vrmUrl ?? '/avatars/wellness-robot.vrm?v=846-shade-lime'
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

    // Find the pill mouth mesh + its 'open' morph target index.
    // SkinnedMesh.scale doesn't reliably animate (skin pulls verts back to
    // bone-driven positions); morph targets ARE applied after skinning, so
    // they actually show. Drive morphTargetInfluences[index] from audio.
    const found = vrm.scene.getObjectByName('mesh_mouth')
    if (found && (found as THREE.SkinnedMesh).morphTargetInfluences) {
      mouthMesh = found as THREE.SkinnedMesh
      const dict = mouthMesh.morphTargetDictionary
      if (dict && 'open' in dict) {
        mouthOpenMorphIndex = dict['open']
      }
    }

    // Capture eye meshes by name for the independent droid-zoom animation.
    // The new logo build uses bezel meshes; fall back to the older names.
    eyeL = vrm.scene.getObjectByName('mesh_eye_bezel_l')
        ?? vrm.scene.getObjectByName('mesh_eye_big_l') ?? null
    eyeR = vrm.scene.getObjectByName('mesh_eye_bezel_r')
        ?? vrm.scene.getObjectByName('mesh_eye_big_r') ?? null
    if (eyeL) eyeBaseScale.L.copy(eyeL.scale)
    if (eyeR) eyeBaseScale.R.copy(eyeR.scale)

    // Capture the photoreceptor material once. JS will drive emissiveIntensity
    // off the same RMS signal that drives mouth-open, so the eyes glow cyan
    // while talking and go dark while silent.
    vrm.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh
      if (!mesh.isMesh || photoMat) return
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      for (const mat of mats) {
        if (mat && mat.name === 'mat_eye_photoreceptor') {
          photoMat = mat as typeof photoMat
          if (photoMat && 'emissiveIntensity' in photoMat) {
            photoBaseEmissiveIntensity = photoMat.emissiveIntensity ?? 0
          }
          return
        }
      }
    })

    // Capture the visor material so mood can drive its emissive color.
    // MToon materials (VRMC_materials_mtoon) get re-keyed by three-vrm; we
    // walk every mesh and pick the first material named 'mat_visor_static'.
    // Falls back silently if absent (non-robot VRMs).
    vrm.scene.traverse((obj) => {
      const m = obj as THREE.Mesh
      if (!m.isMesh || visorMaterial) return
      const mats = Array.isArray(m.material) ? m.material : [m.material]
      for (const mat of mats) {
        if (mat && mat.name === 'mat_visor_static') {
          visorMaterial = mat as THREE.MeshStandardMaterial
          if ((visorMaterial as THREE.MeshStandardMaterial).emissive) {
            visorBaseEmissive.copy((visorMaterial as THREE.MeshStandardMaterial).emissive)
          }
          visorBaseEmissiveIntensity = (visorMaterial as THREE.MeshStandardMaterial).emissiveIntensity ?? 1.0
          break
        }
      }
    })
    // AAA cel-shading pass — walk every material the VRM ships with and
    // crank MToon's shading parameters. shadingToonyFactor at 1.0 produces
    // hard cel bands (no gradient between lit/shadow). shadingShiftFactor
    // lifts the shadow line up the model so the lit area dominates.
    // matcapFactor and rimColor pump in the cyan rim highlight even when
    // the scene's rim light is occluded by geometry. Non-MToon materials
    // are skipped silently.
    vrm.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh
      if (!mesh.isMesh) return
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      for (const mat of mats) {
        if (!mat) continue
        const m = mat as THREE.Material & {
          shadingToonyFactor?: number
          shadingShiftFactor?: number
          rimColorFactor?: THREE.Color
          rimLightingMixFactor?: number
          parametricRimColorFactor?: THREE.Color
          parametricRimFresnelPowerFactor?: number
          parametricRimLiftFactor?: number
        }
        if ('shadingToonyFactor' in m) m.shadingToonyFactor = 0.95
        if ('shadingShiftFactor' in m) m.shadingShiftFactor = -0.15
        if ('parametricRimColorFactor' in m) {
          m.parametricRimColorFactor = new THREE.Color(0x88c8ff)
        }
        if ('parametricRimFresnelPowerFactor' in m) m.parametricRimFresnelPowerFactor = 3.0
        if ('parametricRimLiftFactor' in m) m.parametricRimLiftFactor = 0.0
        if ('rimLightingMixFactor' in m) m.rimLightingMixFactor = 0.6
      }
    })

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

      // ── Mood targeting ──
      // Interpolate moodSmoothed toward the current props.mood target,
      // weighted by moodIntensity (intensity 0 falls back to neutral). This
      // is the single place mood propagates into the avatar — emission +
      // posture + idle tempo all read off moodSmoothed below.
      const tgt = MOOD_TARGETS[props.mood] || MOOD_TARGETS.neutral
      const neu = MOOD_TARGETS.neutral
      const k = Math.max(0, Math.min(1, props.moodIntensity))
      const want = {
        r: neu.visor.r + (tgt.visor.r - neu.visor.r) * k,
        g: neu.visor.g + (tgt.visor.g - neu.visor.g) * k,
        b: neu.visor.b + (tgt.visor.b - neu.visor.b) * k,
        strength: neu.visor.strength + (tgt.visor.strength - neu.visor.strength) * k,
        breathRate: 1.0 + (tgt.breathRate - 1.0) * k,
        swayRate:   1.0 + (tgt.swayRate - 1.0) * k,
        headTiltX:  tgt.headTiltX * k,
        spineTiltX: tgt.spineTiltX * k,
      }
      const ease = Math.min(1, dt * 4)
      moodSmoothed.r          += (want.r - moodSmoothed.r) * ease
      moodSmoothed.g          += (want.g - moodSmoothed.g) * ease
      moodSmoothed.b          += (want.b - moodSmoothed.b) * ease
      moodSmoothed.strength   += (want.strength - moodSmoothed.strength) * ease
      moodSmoothed.breathRate += (want.breathRate - moodSmoothed.breathRate) * ease
      moodSmoothed.swayRate   += (want.swayRate - moodSmoothed.swayRate) * ease
      moodSmoothed.headTiltX  += (want.headTiltX - moodSmoothed.headTiltX) * ease
      moodSmoothed.spineTiltX += (want.spineTiltX - moodSmoothed.spineTiltX) * ease

      // Apply visor emission. MToon stores emissive on .emissive — we write
      // the smoothed RGB directly and scale .emissiveIntensity for "glow".
      if (visorMaterial && (visorMaterial as THREE.MeshStandardMaterial).emissive) {
        const mat = visorMaterial as THREE.MeshStandardMaterial
        mat.emissive.setRGB(moodSmoothed.r, moodSmoothed.g, moodSmoothed.b)
        mat.emissiveIntensity = visorBaseEmissiveIntensity * moodSmoothed.strength
      }

      // Breathing — slow sine on chest+spine, ~14 cycles/min. Bumps when
      // talking so the body 'breathes harder' as it speaks. Rate is mood-
      // modulated (faster for happy/angry, slower for sad/relaxed).
      const ampForBody = isFinite(mouthOpenSmoothed) ? mouthOpenSmoothed : 0
      const breath = Math.sin(t * 1.4 * moodSmoothed.breathRate) * (0.018 + ampForBody * 0.025)
      if (spine) spine.rotation.x = breath + moodSmoothed.spineTiltX
      if (chest) chest.rotation.x = breath * 0.6 + ampForBody * 0.04
      // Subtle forward chest lean during speech — emphasis on talking
      if (spine) spine.rotation.x += ampForBody * 0.03

      // Weight shift — slow lateral hip sway over ~6s. Gives her a natural
      // standing presence instead of a stock-still T-pose feel.
      const sway = Math.sin(t * 0.55 * moodSmoothed.swayRate)
      if (hips) {
        hips.rotation.z = sway * 0.025
        hips.position.x = sway * 0.015
      }

      // Head — subtle gaze drift + a small nod when speaking, so the body
      // visibly engages with the voice (not just the mouth).
      if (neck) neck.rotation.y = 0
      if (head) {
        head.rotation.y = -sway * 0.04
        // Nod: high-frequency micro-bob (3 Hz) scaled by amp + slow drift,
        // plus the mood head-tilt offset (sad droops, happy lifts, etc.).
        const nod = ampForBody * 0.06 * Math.sin(t * 3)
        head.rotation.x = Math.sin(t * 0.9) * 0.02 + nod + moodSmoothed.headTiltX
      }

      // Arm idle — small inward/outward swing baseline, plus when talking
      // the arms gesture slightly (more visible motion = more 'engaged'
      // robot speaking).
      const armGesture = ampForBody * 0.10
      if (lUA) lUA.rotation.x = Math.sin(t * 0.7) * 0.04 + Math.sin(t * 4) * armGesture
      if (rUA) rUA.rotation.x = Math.sin(t * 0.7 + 0.6) * 0.04 + Math.sin(t * 4 + 1.5) * armGesture

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

      // Eye glow — drive photoreceptor emission strength from the audio
      // amplitude (mouthOpenSmoothed). Idle = dark, talking = bright cyan.
      // Curve: x^0.6 lifts low signals so a soft voice still lights the eyes.
      if (photoMat && 'emissiveIntensity' in photoMat) {
        const amp = isFinite(mouthOpenSmoothed) ? mouthOpenSmoothed : 0
        const lit = Math.pow(Math.min(1, Math.max(0, amp)), 0.6)
        photoMat.emissiveIntensity = 0.1 + lit * 9.0  // 0.1 idle dim, up to ~9 bright
      }

      // Droid eye-zoom — each eye scales independently on a slow sine. Left
      // and right use different frequencies + phase offsets so they look
      // like a Star Wars astromech recalibrating its lens (one widens
      // briefly while the other contracts). Scale range stays tight
      // (0.85..1.15) so the eye stays on the face plate.
      if (eyeL) {
        const sL = 1.0 + Math.sin(t * 0.9 + 0.0) * 0.12 + Math.sin(t * 2.7) * 0.04
        eyeL.scale.set(eyeBaseScale.L.x * sL, eyeBaseScale.L.y * sL, eyeBaseScale.L.z * (sL * 0.7 + 0.3))
      }
      if (eyeR) {
        const sR = 1.0 + Math.sin(t * 1.1 + 1.8) * 0.12 + Math.sin(t * 3.1 + 0.4) * 0.04
        eyeR.scale.set(eyeBaseScale.R.x * sR, eyeBaseScale.R.y * sR, eyeBaseScale.R.z * (sR * 0.7 + 0.3))
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
      // Digital monitor face: 3 mouth segments dance in a waveform pattern
      // driven by audio amplitude with phase-offset sines. Each bar peaks
      // at a different moment, creating visual variety that reads as the
      // mouth forming different shapes for different phonemes — without
      // needing actual viseme/phoneme data from the TTS provider.
      // Idle (mouthOpenSmoothed ~= 0): all bars sit at scale 1.0 (flat line).
      // Loud peaks: bars wave up to ~6x with offsets so middle/sides spike
      // at different times.
      // Drive the 'open' morph target on mesh_mouth from audio amplitude.
      // Morph weight 0 = thin closed line; weight 1 = tall oval (5× height,
      // baked into the shape key). Plus a high-frequency syllable wobble
      // so the mouth has phoneme-rate jitter, not just smooth envelope.
      if (mouthMesh && mouthOpenMorphIndex >= 0 && mouthMesh.morphTargetInfluences) {
        const amp = isFinite(mouthOpenSmoothed) ? mouthOpenSmoothed : 0
        const wobble = amp * 0.15 * Math.sin(t * 22)
        const w = Math.max(0, Math.min(1, amp + wobble))
        mouthMesh.morphTargetInfluences[mouthOpenMorphIndex] = w
      }
      const jaw = hum?.getNormalizedBoneNode('jaw')
      if (jaw) jaw.rotation.x = 0  // mandible stays closed; talking is on-visor
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
  mouthOpenMorphIndex = -1
  visorMaterial = null
  eyeL = null
  eyeR = null
  photoMat = null
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
