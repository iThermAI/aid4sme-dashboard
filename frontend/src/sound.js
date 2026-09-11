// Short two-tone alarm through Web Audio. The context is created on a user
// gesture (the Start button), as browsers require.
let ctx = null
export let enabled = true

export function unlock () {
  try {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)()
    if (ctx.state === 'suspended') ctx.resume()
  } catch (e) { ctx = null }
}

export function setEnabled (on) { enabled = on }

export function alarm () {
  if (!enabled || !ctx) return
  const t0 = ctx.currentTime
  ;[0, 0.28].forEach((dt, i) => {
    const o = ctx.createOscillator()
    const g = ctx.createGain()
    o.type = 'sine'
    o.frequency.value = i ? 660 : 880
    g.gain.setValueAtTime(0.0001, t0 + dt)
    g.gain.exponentialRampToValueAtTime(0.25, t0 + dt + 0.02)
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.24)
    o.connect(g).connect(ctx.destination)
    o.start(t0 + dt)
    o.stop(t0 + dt + 0.26)
  })
}
