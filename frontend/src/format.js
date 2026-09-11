export function clock (seconds) {
  const s = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${String(m).padStart(2, '0')}:${ss}`
}

export function timeOfDay (iso) {
  const m = /T(\d\d:\d\d:\d\d)/.exec(iso || '')
  return m ? m[1] : iso || ''
}

export function hhmm (iso) {
  const m = /T(\d\d:\d\d)/.exec(iso || '')
  return m ? m[1] : iso || ''
}

export function dateTime (iso) {
  const m = /^(\d{4}-\d\d-\d\d)T(\d\d:\d\d)/.exec(iso || '')
  return m ? `${m[1]} ${m[2]}` : iso || ''
}

export function mb (v) {
  if (v === null || v === undefined) return '\u2013'
  return v >= 1000 ? `${(v / 1000).toFixed(2)} GB` : `${v.toFixed(v < 10 ? 1 : 0)} MB`
}

export function num (v, digits = 1) {
  return v === null || v === undefined || Number.isNaN(Number(v)) ? '\u2013' : Number(v).toFixed(digits)
}

export function signedMs (v) {
  if (v === null || v === undefined) return '\u2013'
  return `${v > 0 ? '+' : v < 0 ? '\u2212' : ''}${Math.abs(v).toFixed(0)} ms`
}

export function runNo (n) {
  return String(n || 0).padStart(3, '0')
}

export function incrementTrailing (value) {
  const m = /^(.*?)(\d+)(\D*)$/.exec(value || '')
  if (!m) return value
  return m[1] + String(Number(m[2]) + 1).padStart(m[2].length, '0') + m[3]
}
