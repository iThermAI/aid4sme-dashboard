async function request (method, url, body) {
  const init = { method, headers: {} }
  if (body instanceof Blob) {
    init.body = body
    init.headers['Content-Type'] = 'application/octet-stream'
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(url, init)
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch (e) { data = text }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `generic:${res.status} ${res.statusText}`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

const enc = encodeURIComponent

export const api = {
  status: () => request('GET', '/api/status'),
  config: () => request('GET', '/api/config'),
  prefs: (p) => request('PUT', '/api/preferences', p),

  draft: () => request('GET', '/api/draft'),
  saveMetadata: (md) => request('PUT', '/api/draft/metadata', md),
  saveOptions: (o) => request('PUT', '/api/draft/options', o),
  saveRegions: (stream, regions) => request('PUT', `/api/draft/regions/${stream}`, { regions }),
  uploadCad: (file) => request('PUT', `/api/draft/cad?filename=${enc(file.name)}`, file),
  removeCad: () => request('DELETE', '/api/draft/cad'),

  parts: () => request('GET', '/api/parts'),
  savePart: (name) => request('POST', '/api/parts', { name }),
  applyPart: (slug) => request('POST', `/api/parts/${enc(slug)}/apply`),
  deletePart: (slug) => request('DELETE', `/api/parts/${enc(slug)}`),

  camera: (id) => request('GET', `/api/cameras/${enc(id)}`),
  checkCameras: () => request('POST', '/api/cameras/check'),
  renameChannel: (id, kind, name) => request('PUT', `/api/cameras/${enc(id)}/channel-name`, { kind, name }),
  ffc: (id) => request('POST', `/api/cameras/${enc(id)}/ffc`),

  profiles: () => request('GET', '/api/profiles'),
  saveProfile: (name, note, reference) => request('POST', '/api/profiles', { name, note, reference }),
  profilePreview: (slug) => request('GET', `/api/profiles/${enc(slug)}/preview`),
  restoreProfile: (slug, cameras) => request('POST', `/api/profiles/${enc(slug)}/restore`, { cameras }),
  deleteProfile: (slug) => request('DELETE', `/api/profiles/${enc(slug)}`),

  connections: () => request('GET', '/api/settings/connections'),
  testConnection: (c) => request('POST', '/api/settings/connections/test', c),
  saveConnections: (cameras) => request('PUT', '/api/settings/connections', { cameras }),

  start: () => request('POST', '/api/record/start'),
  stop: () => request('POST', '/api/record/stop'),
  note: (note) => request('POST', '/api/record/note', { note }),
  acknowledge: () => request('POST', '/api/result/acknowledge'),

  sessions: () => request('GET', '/api/sessions'),
  session: (id) => request('GET', `/api/sessions/${enc(id)}`),
  verdict: (id, verdict, reason) => request('PUT', `/api/sessions/${enc(id)}/verdict`, { verdict, reason })
}
