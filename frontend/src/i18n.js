import { ref } from 'vue'

export const locale = ref('en')

const en = {
  app: { name: 'Aid4SME Dashboard', tagline: 'Multi-modal capture for injection moulding' },
  nav: { run: 'Run', sessions: 'Sessions', cameras: 'Cameras', settings: 'Settings', about: 'About' },
  state: {
    connecting: 'Connecting', ready: 'Ready to record', notReady: 'Not ready', starting: 'Starting',
    recording: 'Recording', stopping: 'Stopping', verifying: 'Checking files', finished: 'Run finished'
  },
  common: {
    save: 'Save', cancel: 'Cancel', delete: 'Delete', refresh: 'Refresh', close: 'Close', edit: 'Edit',
    loading: 'Loading…', saving: 'Saving…', saved: 'Saved', optional: 'optional', yes: 'Yes', no: 'No',
    on: 'On', off: 'Off', unknown: 'Unknown', none: 'None', test: 'Test', apply: 'Apply', back: 'Back',
    gbFree: '{v} GB free', hoursLeft: '≈ {v} h of recording space', minutes: 'min', seconds: 's'
  },
  stream: {
    optical: 'optical', thermal: 'thermal', radiometric: 'temperature data', keyence: 'Keyence OCR',
    camera: 'Camera {n}'
  },
  field: {
    operator: 'Operator', mould_id: 'Mould ID', part_number: 'Part number', material: 'Material',
    shot_counter_start: 'Shot counter', thermal_range: 'Camera temperature range', notes: 'Notes'
  },
  conn: {
    offline: 'The dashboard server is not answering. Check that it is still running on the capture PC. Retrying every second.',
    waiting: 'Connecting to the dashboard server…'
  },
  setup: {
    previews: 'Camera views',
    hint: 'Scroll to zoom, drag to move the view. Draw regions with the “Add region” tool. Zooming never changes a region, and recordings are always full frame.',
    runDetails: 'Run details',
    preset: 'Part preset', presetNone: 'No preset', presetSave: 'Save as preset', presetName: 'Preset name',
    presetSaved: 'Preset saved', presetHint: 'Loads mould, part, material, regions and part model in one step.',
    runNumber: 'Run {n}', runOfMould: 'next run for mould {m}', runNoMould: 'enter a mould ID',
    autoInc: 'increases after each run',
    stopAfter: 'Stop automatically', manualStop: 'No, stop manually', customMinutes: 'Other…',
    rangeHint: 'Must match the range set on both cameras; readings at the ceiling are flagged.',
    partModel: 'Part model', loadGlb: 'Load .glb file', replace: 'Replace', remove: 'Remove',
    cadEmpty: 'Load the part’s .glb file so the operator can confirm which part is being moulded.',
    cadError: 'The model could not be displayed. Only uncompressed .glb files are supported.',
    noWebgl: 'This browser cannot show 3D here. The model is still stored with each session.',
    devices: 'Devices', online: 'Online', offline: 'Not responding', checking: 'Checking…',
    clockOk: 'Clock in step', clockOff: 'Clock {v} s off',
    settingsOk: 'Settings as recommended', settingsWarn: 'Check {n} settings', settingsChanged: '{n} changed since profile',
    keyenceNone: 'Not recording', keyenceIv3: 'IV3, image every {v} s', keyenceWaiting: 'Waiting for the first image',
    keyenceHint: 'The IV3 photographs the machine screen. Regions mark the fields to be read later; they change nothing in the recording.',
    start: 'Start recording', startingBtn: 'Starting…'
  },
  view: {
    addRegion: 'Add region', zoomIn: 'Zoom in', zoomOut: 'Zoom out', fit: 'Fit to frame', expand: 'Enlarge',
    shrink: 'Back to all cameras', regionName: 'Region name', deleteRegion: 'Delete region', region: 'Region',
    regions: 'regions', waiting: 'Waiting for the first image…', cursor: 'At cursor',
    stats: 'min {min} · max {max} · mean {mean} °C', drawHint: 'Drag on the image to draw the region'
  },
  rec: {
    recording: 'Recording', stopsAt: 'Stops automatically at {t}', plannedStop: 'Planned stop at {t}',
    stop: 'Stop recording', confirmStop: 'Click again to stop', run: 'Run {n}',
    closing: { starting: 'Saving camera settings and starting streams', stopping: 'Stopping streams and closing files', verifying: 'Checking the recorded files' },
    streamDown: '{s} has stopped. The other streams are still recording. Check the camera and network; if it does not recover, stop and restart the run.',
    streamStalled: '{s} is not delivering data. The other streams are still recording.',
    saturated: 'Temperatures at the top of the {r} range were measured by {s}. Hot areas may be clipped; if it repeats, switch both cameras to the high range.',
    table: { stream: 'Stream', status: 'Status', rate: 'Rate', written: 'Written', last: 'Last data', minute: 'Last minute', details: 'Details' },
    health: { ok: 'Recording', starting: 'Connecting', stalled: 'No data', dead: 'Stopped', stopping: 'Stopping', stopped: 'Stopped', off: 'Not connected' },
    frames: '{n} frames, {m} Mbit/s', images: '{n} images, {t} triggers', triggerNo: 'trigger no. {v}', maxT: 'max {v} °C', response: 'response {v} ms', freezes: '{n} shutter freezes',
    failed: '{n} failed', ceiling: '{n} at range ceiling', shutter: 'shutter',
    notes: 'Notes during the run', notesHint: 'Saved with the exact time, e.g. “short shot”, “mould opened”.',
    notePlaceholder: 'What happened?', addNote: 'Add note', events: 'Recent events',
    sound: 'Alarm sound', soundOn: 'Alarm sound on', soundOff: 'Alarm sound off'
  },
  event: {
    session_created: 'Session created', config_snapshot_done: 'Camera settings saved', stream_started: 'Stream started',
    recording_started: 'Recording started', stream_health: 'Stream status changed', operator_note: 'Note added',
    stop_requested: 'Stop requested', stream_finished: 'Stream closed', capture_stopped: 'Capture stopped',
    verification_done: 'Files checked', session_closed: 'Session closed', range_saturation: 'Range ceiling reached',
    ffc_freeze_start: 'Shutter calibration', ffc_freeze_end: 'Shutter calibration ended',
    radiometric_error: 'Temperature data request failed', radiometric_stopped: 'Temperature data stopped',
    keyence_connected: 'Keyence connected', keyence_error: 'Keyence connection error',
    keyence_ftp_started: 'Keyence image server started', keyence_receive_only: 'Keyence: receiving images only', keyence_connect_failed: 'Keyence not reachable', start_failed: 'Start failed'
  },
  stopReason: {
    operator: 'Stopped by the operator', planned_duration: 'Planned duration reached',
    max_duration: 'Maximum run length reached', disk_full: 'Disk nearly full', server_shutdown: 'Server shut down',
    start_failed: 'The recording could not start', server_stopped: 'Server stopped during the run'
  },
  summary: {
    ok: 'All streams recorded completely', bad: 'The run finished with problems',
    recorded: '{t} recorded', folder: 'Session folder', openFolder: 'Open folder',
    openFolderHint: 'Opens on the capture PC, not on this screen.',
    startFailed: 'Nothing was recorded. Reason: {d}',
    verdict: 'Is this run usable for the dataset?', usable: 'Usable', discard: 'Discard', unsure: 'Not sure',
    reason: 'Reason (optional)', reasonPlaceholder: 'e.g. short shot, mould not at temperature',
    verdictSaved: 'Saved with the session',
    next: 'Set up next run', nextKeeps: 'Run details, regions and part model are kept.',
    willChange: '{f} becomes {v}', badHint: 'The session is kept and marked for checking. Details are in verification.json in the session folder.'
  },
  verify: {
    stream: 'Stream', result: 'Result', recorded: 'Recorded', offset: 'Start offset', notes: 'Notes',
    complete: 'Complete', problem: 'Problem', framesIn: '{n} frames in {s} s', matrices: '{n} matrices, {r}/s',
    late: 'started {v} s late', missing: '{v} % frames missing', interrupted: 'interrupted during run',
    ffmpegWarn: '{n} FFmpeg warnings', timing: 'timing ±{v} ms',
    offsetNote: 'Start offsets are estimated from when data reached the capture PC. They exclude each camera’s internal delay: a first check, not the final alignment.'
  },
  sessions: {
    title: 'Recorded sessions', count: '{n} sessions', search: 'Filter by mould, part, material or operator',
    empty: 'No sessions yet. Recordings appear here when a run is stopped.',
    started: 'Started', run: 'Run', length: 'Length', mould: 'Mould', part: 'Part', material: 'Material',
    operator: 'Operator', result: 'Result', verdict: 'Verdict', size: 'Size', simulated: 'simulated',
    status: { complete: 'Complete', check: 'Check', failed: 'Failed', interrupted: 'Interrupted', recording: 'Recording' }
  },
  cameras: {
    title: 'Cameras', refreshed: 'Read from the cameras at {t}', refreshAll: 'Read again',
    autoRefresh: 'Values are read live from each camera and again whenever you return to this page.',
    openWeb: 'Open camera web page', model: 'Model', serial: 'Serial number', firmware: 'Firmware', mac: 'MAC address',
    timeMode: 'Time source', ntpServer: 'NTP server', clock: 'Clock offset',
    nameOnVideo: 'Name shown on the video', nameShown: 'shown on video', nameHidden: 'not shown on video',
    rename: 'Rename', renameSaved: 'Name updated on the camera', renameFailed: 'The camera did not accept the new name',
    checks: 'Settings check', streams: 'Video streams', thermal: 'Thermal image and measurement', device: 'Device and time',
    allValues: 'All values read from the camera', endpoint: 'Endpoint', notAvailable: 'not available on this camera',
    attr: {
      codec: 'Codec', resolution: 'Resolution', fps: 'Frame rate', bitrate: 'Bitrate', gop: 'Keyframe interval',
      palette: 'Palette', agc: 'Contrast mode (AGC)', dde: 'Detail enhancement', display_mode: 'Display mode',
      ffc_mode: 'Shutter calibration', range: 'Temperature range', emissivity: 'Emissivity', distance: 'Distance',
      reflective: 'Reflected temperature', measurement_overlay: 'Measurement overlay on video',
      level_span: 'Level and span', noise_reduction: 'Temporal noise reduction', digital_zoom: 'Digital zoom',
      p2p_emissivity: 'Emissivity (temperature data)', p2p_distance: 'Distance (temperature data)',
      p2p_refresh: 'Temperature data refresh (s)'
    },
    distanceHint: 'Set this to the real distance between camera and part, in the camera’s web page. It changes every temperature value recorded.',
    fieldSource: 'read from {s}', unknownField: 'Not identified yet for this firmware',
    ffc: 'Calibrate shutter now', ffcDone: 'Shutter calibration triggered',
    keyenceTitle: 'Keyence IV3', keyenceTrigger: 'Take a picture now', keyenceTriggered: 'Picture received, trigger no. {v}',
    keyenceNoPicture: 'No picture arrived. Check the camera\u2019s FTP output settings and the firewall.',
    keyenceLast: 'Last picture', keyenceAge: '{v} s ago', keyenceImages: 'Pictures this session',
    keyenceInterval: 'Picture every', keyenceFtpPort: 'FTP port on this PC', keyencePort: 'Trigger port',
    keyenceResult: 'Latest result from the camera', keyenceMode: 'Recording mode',
    keyenceTriggerMode: 'Trigger', keyenceTriggerOn: 'The dashboard triggers the camera',
    keyenceTriggerOff: 'The camera triggers itself',
    keyenceRefused: 'The camera refused the trigger command ({v}); recording whatever it sends by itself.',
    keyenceModeOff: 'Off', keyenceModeIv3: 'IV3 images',
    frames: '{v} fps', gopFrames: '{v} frames'
  },
  check: {
    resolution: 'Resolution {v}, expected {e}', fps: 'Frame rate {v} fps, expected {e}',
    gop: 'Keyframe every {v} frames, expected {e} (one per second)', bitrate_type: 'Bitrate mode {v}, expected {e}',
    codec: 'Codec {v}; {e} is recommended (half the storage)', osd_time: 'Date and time shown on the video (time display must be on)',
    ntp: 'Time source {v}; NTP is recommended', clock: 'Clock offset {v} s',
    palette: 'Palette {v}; White Hot is recommended', agc: 'Contrast mode {v}; Linear is recommended',
    dde: 'Detail enhancement {v}; Off is recommended', display_mode: 'Display mode {v}; pure thermal is recommended',
    measurement_overlay: 'Measurement graphics on the video: {v}; Off is recommended',
    range: 'Camera range {v}; run details say {e}',
    emissivity_vs_reference: 'Emissivity {v}; profile has {e}', distance_vs_reference: 'Distance {v}; profile has {e}',
    level_span: 'Level and span {v}; manual is recommended, so grey levels mean the same temperature in every frame',
    noise_reduction: 'Temporal noise reduction level {v}; 0 is recommended',
    digital_zoom: 'Digital zoom {v}; 1x is required for regions to map onto the temperature data',
    p2p_refresh: 'Temperature data refreshed every {v} s; 1 s is needed for one new matrix per second',
    p2p_mismatch: 'Temperature data uses {v}, measurement settings use {e}; they should match',
    rules_enabled: '{v} measurement rules active; none is recommended',
    unknown: 'Not identified yet for this firmware'
  },
  profiles: {
    title: 'Camera settings profiles',
    intro: 'A profile stores the image, stream and measurement settings of both cameras. The reference profile is compared with the live cameras before every run; restore brings the cameras back to it. Network settings and user accounts are never changed.',
    reference: 'Reference', useReference: 'Use as reference', clearReference: 'Clear reference', noReference: 'No reference profile',
    empty: 'No profiles yet. Configure both cameras, then save their settings here.',
    saveNew: 'Save current settings', name: 'Profile name', note: 'Note', makeReference: 'Use as reference',
    restore: 'Restore…', restoreTitle: 'Restore “{n}”', restoreIntro: 'These camera settings will be written back:',
    noChanges: 'Already identical to the profile.', restoreBtn: 'Restore settings', restored: 'Restore finished',
    remaining: '{n} values could not be restored; see the list.', deleteConfirm: 'Delete profile “{n}”?',
    created: 'saved {t}', changesVsRef: '{n} settings differ from “{p}”', matchesRef: 'Matches “{p}”'
  },
  settings: {
    title: 'Settings',
    connections: 'Camera connections',
    connectionsHint: 'Address, user and password the dashboard uses to reach each camera. Leave the password empty to keep the current one.',
    address: 'Address', user: 'User', password: 'Password', passwordKeep: 'unchanged', saveConnections: 'Save connections',
    testOk: 'Connected: {m}', testUnauthorized: 'Wrong user or password', testUnreachable: 'Not reachable', testHttp: 'Camera answered HTTP {v}',
    connectionsSaved: 'Connections saved',
    numbering: 'After each run',
    numberingHint: 'Chosen fields increase their trailing number after every finished run, e.g. M-012 becomes M-013. Run numbers per mould are always counted automatically.',
    language: 'Language', theme: 'Appearance', light: 'Light', dark: 'Dark',
    backup: 'Full camera backup',
    backupHint: 'The camera’s own complete backup file, for administrators. It can only be restored in the camera’s web page.',
    download: 'Download', system: 'System', configFile: 'Configuration file', dataDir: 'Data folder', ffmpeg: 'FFmpeg',
    simulation: 'Simulation mode'
  },
  about: {
    title: 'About',
    text: 'Aid4SME Dashboard captures synchronised optical video, thermal video, radiometric temperature data and process parameters from an injection moulding cell, for machine learning.',
    partners: 'Developed by iThermAI together with Elvez.',
    funding: 'This work was supported by the AID4SME project, funded by the European Union’s Horizon Europe programme under grant agreement No 101189562.',
    version: 'Version {v}', license: 'Proprietary software of iThermAI and Elvez. All rights reserved.'
  },
  blocker: {
    missing_fields: 'Enter the {f}.', camera_checking: 'Checking {c}…', camera_offline: '{c} ({ip}) is not responding.',
    camera_auth: '{c} ({ip}) rejected the user name or password. Logins to it are paused so its account is not locked; correct it in Settings and press Test.',
    disk_low: 'Only {free} GB free on the data drive; {need} GB needed.', ffmpeg_missing: 'FFmpeg was not found ({path}).'
  },
  warning: {
    clock_drift: '{c} clock is {v} s off the capture PC.', settings_changed: '{c}: {n} settings differ from the reference profile.',
    settings_not_recommended: '{c}: {n} settings differ from the recommendation.', no_reference: 'No reference camera profile chosen yet.',
    no_regions: 'No regions drawn.', no_cad: 'No part model loaded.',
    keyence_offline: 'The Keyence IV3 ({ip}) is not answering; its images will be missing from this run.'
  },
  error: {
    busy_recording: 'Not possible while a recording is running.', previews_paused: 'Previews are paused while recording.',
    blocked: 'Recording can’t start yet; see the list above the button.', not_recording: 'No recording is running.',
    start_failed: 'The recording could not start: {d}', invalid_name: 'Use 1–32 characters, without < or >.',
    name_not_supported: 'This camera does not offer a channel name setting.', name_required: 'Enter a name.',
    invalid_address: 'Enter an IP address or host name, e.g. 192.168.1.30.', user_required: 'Enter the user name.',
    invalid_duration: 'Enter a duration in minutes.', not_glb: 'That is not a binary glTF (.glb) file.',
    camera_offline: '{d} is not responding.', not_found: 'Not found.',
    cannot_open_folder: 'The folder could not be opened on the capture PC: {d}', ffc_not_configured: 'Shutter calibration is not configured.',
    generic: 'Something went wrong: {d}'
  }
}

const sl = {
  app: { name: 'Aid4SME Dashboard', tagline: 'Večmodalni zajem za brizganje plastike' },
  nav: { run: 'Priprava', sessions: 'Posnetki', cameras: 'Kamere', settings: 'Nastavitve', about: 'O programu' },
  state: {
    connecting: 'Povezovanje', ready: 'Pripravljeno za snemanje', notReady: 'Ni pripravljeno', starting: 'Zagon',
    recording: 'Snemanje', stopping: 'Ustavljanje', verifying: 'Preverjanje datotek', finished: 'Snemanje končano'
  },
  common: {
    save: 'Shrani', cancel: 'Prekliči', delete: 'Izbriši', refresh: 'Osveži', close: 'Zapri', edit: 'Uredi',
    loading: 'Nalaganje …', saving: 'Shranjevanje …', saved: 'Shranjeno', optional: 'neobvezno', yes: 'Da', no: 'Ne',
    on: 'Vklopljeno', off: 'Izklopljeno', unknown: 'Neznano', none: 'Brez', test: 'Preizkusi', apply: 'Uporabi', back: 'Nazaj',
    gbFree: 'prostih {v} GB', hoursLeft: 'prostora za ≈ {v} h snemanja', minutes: 'min', seconds: 's'
  },
  stream: {
    optical: 'optična', thermal: 'termalna', radiometric: 'temperaturni podatki', keyence: 'Keyence OCR',
    camera: 'Kamera {n}'
  },
  field: {
    operator: 'Operater', mould_id: 'Oznaka orodja', part_number: 'Številka izdelka', material: 'Material',
    shot_counter_start: 'Števec ciklov', thermal_range: 'Temperaturno območje kamere', notes: 'Opombe'
  },
  conn: {
    offline: 'Strežnik se ne odziva. Preverite, ali na računalniku za zajem še teče. Nov poskus vsako sekundo.',
    waiting: 'Povezovanje s strežnikom …'
  },
  setup: {
    previews: 'Pogledi kamer',
    hint: 'Z vrtenjem kolesca povečate, z vlečenjem premaknete pogled. Območja narišete z orodjem »Dodaj območje«. Povečava nikoli ne spremeni območja; posnetki so vedno v polni sliki.',
    runDetails: 'Podatki o snemanju',
    preset: 'Prednastavitev izdelka', presetNone: 'Brez prednastavitve', presetSave: 'Shrani kot prednastavitev', presetName: 'Ime prednastavitve',
    presetSaved: 'Prednastavitev shranjena', presetHint: 'Naenkrat naloži orodje, izdelek, material, območja in 3D model.',
    runNumber: 'Snemanje {n}', runOfMould: 'naslednje za orodje {m}', runNoMould: 'vnesite oznako orodja',
    autoInc: 'se poveča po vsakem snemanju',
    stopAfter: 'Samodejna ustavitev', manualStop: 'Ne, ročna ustavitev', customMinutes: 'Drugo …',
    rangeHint: 'Mora se ujemati z območjem na obeh kamerah; meritve na zgornji meji so označene.',
    partModel: '3D model izdelka', loadGlb: 'Naloži datoteko .glb', replace: 'Zamenjaj', remove: 'Odstrani',
    cadEmpty: 'Naložite datoteko .glb izdelka, da operater lahko potrdi, kateri izdelek se brizga.',
    cadError: 'Modela ni mogoče prikazati. Podprte so le nestisnjene datoteke .glb.',
    noWebgl: 'Ta brskalnik tu ne more prikazati 3D. Model se kljub temu shrani z vsakim posnetkom.',
    devices: 'Naprave', online: 'Povezana', offline: 'Se ne odziva', checking: 'Preverjanje …',
    clockOk: 'Ura usklajena', clockOff: 'Ura odstopa {v} s',
    settingsOk: 'Nastavitve kot priporočeno', settingsWarn: 'Preverite nastavitve ({n})', settingsChanged: 'Spremenjeno glede na profil: {n}',
    keyenceNone: 'Se ne snema', keyenceIv3: 'IV3, slika vsakih {v} s', keyenceWaiting: 'Čakanje na prvo sliko',
    keyenceHint: 'IV3 fotografira zaslon stroja. Območja označujejo polja za kasnejše branje; na posnetek ne vplivajo.',
    start: 'Začni snemanje', startingBtn: 'Zagon …'
  },
  view: {
    addRegion: 'Dodaj območje', zoomIn: 'Povečaj', zoomOut: 'Pomanjšaj', fit: 'Prilagodi sliki', expand: 'Povečaj pogled',
    shrink: 'Nazaj na vse kamere', regionName: 'Ime območja', deleteRegion: 'Izbriši območje', region: 'Območje',
    regions: 'območja', waiting: 'Čakanje na prvo sliko …', cursor: 'Pod kazalcem',
    stats: 'min {min} · maks {max} · povpr. {mean} °C', drawHint: 'Povlecite po sliki, da narišete območje'
  },
  rec: {
    recording: 'Snemanje', stopsAt: 'Samodejna ustavitev pri {t}', plannedStop: 'Načrtovana ustavitev pri {t}',
    stop: 'Ustavi snemanje', confirmStop: 'Kliknite znova za ustavitev', run: 'Snemanje {n}',
    closing: { starting: 'Shranjevanje nastavitev kamer in zagon tokov', stopping: 'Ustavljanje tokov in zapiranje datotek', verifying: 'Preverjanje posnetih datotek' },
    streamDown: '{s} se je ustavil(a). Ostali tokovi se še snemajo. Preverite kamero in omrežje; če se ne obnovi, ustavite in znova začnite snemanje.',
    streamStalled: '{s} ne pošilja podatkov. Ostali tokovi se še snemajo.',
    saturated: '{s} je izmeril(a) temperature na zgornji meji območja {r}. Vroča mesta so lahko odrezana; če se ponovi, obe kameri preklopite na visoko območje.',
    table: { stream: 'Tok', status: 'Stanje', rate: 'Hitrost', written: 'Zapisano', last: 'Zadnji podatki', minute: 'Zadnja minuta', details: 'Podrobnosti' },
    health: { ok: 'Snemanje', starting: 'Povezovanje', stalled: 'Ni podatkov', dead: 'Ustavljeno', stopping: 'Ustavljanje', stopped: 'Ustavljeno', off: 'Ni povezano' },
    frames: '{n} sličic, {m} Mbit/s', images: 'slik: {n}, prožitev: {t}', triggerNo: 'št. prožitve {v}', maxT: 'maks. {v} °C', response: 'odziv {v} ms', freezes: 'kalibracij zaklopa: {n}',
    failed: 'neuspelih: {n}', ceiling: 'na zgornji meji: {n}', shutter: 'zaklop',
    notes: 'Opombe med snemanjem', notesHint: 'Shranijo se s točnim časom, npr. »nepopoln izdelek«, »orodje odprto«.',
    notePlaceholder: 'Kaj se je zgodilo?', addNote: 'Dodaj opombo', events: 'Zadnji dogodki',
    sound: 'Zvočni alarm', soundOn: 'Zvočni alarm vklopljen', soundOff: 'Zvočni alarm izklopljen'
  },
  event: {
    session_created: 'Posnetek ustvarjen', config_snapshot_done: 'Nastavitve kamer shranjene', stream_started: 'Tok zagnan',
    recording_started: 'Snemanje začeto', stream_health: 'Stanje toka spremenjeno', operator_note: 'Opomba dodana',
    stop_requested: 'Zahtevana ustavitev', stream_finished: 'Tok zaprt', capture_stopped: 'Zajem ustavljen',
    verification_done: 'Datoteke preverjene', session_closed: 'Posnetek zaključen', range_saturation: 'Dosežena zgornja meja območja',
    ffc_freeze_start: 'Kalibracija zaklopa', ffc_freeze_end: 'Kalibracija zaklopa končana',
    radiometric_error: 'Zahteva za temperaturne podatke ni uspela', radiometric_stopped: 'Temperaturni podatki ustavljeni',
    keyence_connected: 'Keyence povezan', keyence_error: 'Napaka povezave Keyence',
    keyence_ftp_started: 'Strežnik za slike Keyence zagnan', keyence_receive_only: 'Keyence: samo sprejemanje slik', keyence_connect_failed: 'Keyence ni dosegljiv', start_failed: 'Zagon ni uspel'
  },
  stopReason: {
    operator: 'Ustavil operater', planned_duration: 'Dosežen načrtovani čas',
    max_duration: 'Dosežena največja dolžina snemanja', disk_full: 'Disk je skoraj poln', server_shutdown: 'Strežnik zaustavljen',
    start_failed: 'Snemanja ni bilo mogoče začeti', server_stopped: 'Strežnik se je ustavil med snemanjem'
  },
  summary: {
    ok: 'Vsi tokovi so v celoti posneti', bad: 'Snemanje se je končalo s težavami',
    recorded: 'posneto {t}', folder: 'Mapa posnetka', openFolder: 'Odpri mapo',
    openFolderHint: 'Odpre se na računalniku za zajem, ne na tem zaslonu.',
    startFailed: 'Nič ni bilo posneto. Razlog: {d}',
    verdict: 'Je ta posnetek uporaben za podatkovni niz?', usable: 'Uporaben', discard: 'Zavrzi', unsure: 'Ni jasno',
    reason: 'Razlog (neobvezno)', reasonPlaceholder: 'npr. nepopoln izdelek, orodje ni na temperaturi',
    verdictSaved: 'Shranjeno s posnetkom',
    next: 'Pripravi naslednje snemanje', nextKeeps: 'Podatki, območja in 3D model ostanejo.',
    willChange: '{f} postane {v}', badHint: 'Posnetek je shranjen in označen za preverjanje. Podrobnosti so v datoteki verification.json v mapi posnetka.'
  },
  verify: {
    stream: 'Tok', result: 'Rezultat', recorded: 'Posneto', offset: 'Zamik začetka', notes: 'Opombe',
    complete: 'Popolno', problem: 'Težava', framesIn: '{n} sličic v {s} s', matrices: '{n} matrik, {r}/s',
    late: 'začetek {v} s pozneje', missing: 'manjka {v} % sličic', interrupted: 'prekinjeno med snemanjem',
    ffmpegWarn: 'opozorila FFmpeg: {n}', timing: 'čas ±{v} ms',
    offsetNote: 'Zamiki so ocenjeni iz časa prihoda podatkov na računalnik za zajem. Ne vključujejo notranje zakasnitve kamer: prvo preverjanje, ne končna poravnava.'
  },
  sessions: {
    title: 'Posnetki', count: 'posnetkov: {n}', search: 'Filtriraj po orodju, izdelku, materialu ali operaterju',
    empty: 'Posnetkov še ni. Prikažejo se, ko se snemanje ustavi.',
    started: 'Začetek', run: 'Št.', length: 'Dolžina', mould: 'Orodje', part: 'Izdelek', material: 'Material',
    operator: 'Operater', result: 'Rezultat', verdict: 'Ocena', size: 'Velikost', simulated: 'simulirano',
    status: { complete: 'Popolno', check: 'Preveri', failed: 'Neuspelo', interrupted: 'Prekinjeno', recording: 'Snemanje' }
  },
  cameras: {
    title: 'Kamere', refreshed: 'Prebrano s kamer ob {t}', refreshAll: 'Preberi znova',
    autoRefresh: 'Vrednosti se berejo neposredno s kamer in znova vsakič, ko se vrnete na to stran.',
    openWeb: 'Odpri spletno stran kamere', model: 'Model', serial: 'Serijska številka', firmware: 'Programska oprema', mac: 'Naslov MAC',
    timeMode: 'Vir časa', ntpServer: 'Strežnik NTP', clock: 'Odstopanje ure',
    nameOnVideo: 'Ime, prikazano na posnetku', nameShown: 'prikazano na posnetku', nameHidden: 'ni prikazano na posnetku',
    rename: 'Preimenuj', renameSaved: 'Ime na kameri posodobljeno', renameFailed: 'Kamera novega imena ni sprejela',
    checks: 'Preverjanje nastavitev', streams: 'Video tokovi', thermal: 'Termalna slika in merjenje', device: 'Naprava in čas',
    allValues: 'Vse vrednosti, prebrane s kamere', endpoint: 'Vmesnik', notAvailable: 'ni na voljo na tej kameri',
    attr: {
      codec: 'Kodek', resolution: 'Ločljivost', fps: 'Hitrost sličic', bitrate: 'Bitna hitrost', gop: 'Interval ključnih sličic',
      palette: 'Paleta', agc: 'Način kontrasta (AGC)', dde: 'Poudarjanje podrobnosti', display_mode: 'Način prikaza',
      ffc_mode: 'Kalibracija zaklopa', range: 'Temperaturno območje', emissivity: 'Emisivnost', distance: 'Razdalja',
      reflective: 'Odbita temperatura', measurement_overlay: 'Merilna grafika na posnetku',
      level_span: 'Nivo in razpon', noise_reduction: 'Časovno odstranjevanje šuma', digital_zoom: 'Digitalna povečava',
      p2p_emissivity: 'Emisivnost (temperaturni podatki)', p2p_distance: 'Razdalja (temperaturni podatki)',
      p2p_refresh: 'Osveževanje temperaturnih podatkov (s)'
    },
    distanceHint: 'Nastavite na dejansko razdaljo med kamero in izdelkom, na spletni strani kamere. Vpliva na vse posnete temperature.',
    fieldSource: 'prebrano iz {s}', unknownField: 'Za to programsko opremo še ni določeno',
    ffc: 'Kalibriraj zaklop zdaj', ffcDone: 'Kalibracija zaklopa sprožena',
    keyenceTitle: 'Keyence IV3', keyenceTrigger: 'Posnemi sliko zdaj', keyenceTriggered: 'Slika prejeta, št. prožitve {v}',
    keyenceNoPicture: 'Slika ni prispela. Preverite nastavitve FTP na kameri in požarni zid.',
    keyenceLast: 'Zadnja slika', keyenceAge: 'pred {v} s', keyenceImages: 'Slik v tej seji',
    keyenceInterval: 'Slika vsakih', keyenceFtpPort: 'Vrata FTP na tem računalniku', keyencePort: 'Vrata za proženje',
    keyenceResult: 'Zadnji rezultat kamere', keyenceMode: 'Način snemanja',
    keyenceTriggerMode: 'Proženje', keyenceTriggerOn: 'Kamero proži nadzorna plošča',
    keyenceTriggerOff: 'Kamera se proži sama',
    keyenceRefused: 'Kamera je zavrnila ukaz za proženje ({v}); snema se, kar pošlje sama.',
    keyenceModeOff: 'Izklopljeno', keyenceModeIv3: 'Slike IV3',
    frames: '{v} sl./s', gopFrames: '{v} sličic'
  },
  check: {
    resolution: 'Ločljivost {v}, pričakovano {e}', fps: 'Hitrost {v} sl./s, pričakovano {e}',
    gop: 'Ključna sličica vsakih {v} sličic, pričakovano {e} (ena na sekundo)', bitrate_type: 'Način bitne hitrosti {v}, pričakovano {e}',
    codec: 'Kodek {v}; priporočen je {e} (pol manj prostora)', osd_time: 'Datum in čas prikazana na posnetku (prikaz časa mora biti vklopljen)',
    ntp: 'Vir časa {v}; priporočen je NTP', clock: 'Odstopanje ure {v} s',
    palette: 'Paleta {v}; priporočena je White Hot', agc: 'Način kontrasta {v}; priporočen je linearni',
    dde: 'Poudarjanje podrobnosti {v}; priporočeno je izklopljeno', display_mode: 'Način prikaza {v}; priporočen je čisti termalni',
    measurement_overlay: 'Merilna grafika na posnetku: {v}; priporočeno je izklopljeno',
    range: 'Območje kamere {v}; v podatkih o snemanju je {e}',
    emissivity_vs_reference: 'Emisivnost {v}; v profilu je {e}', distance_vs_reference: 'Razdalja {v}; v profilu je {e}',
    level_span: 'Nivo in razpon {v}; priporočen je ročni, da siva vrednost v vseh sličicah pomeni isto temperaturo',
    noise_reduction: 'Časovno odstranjevanje šuma, nivo {v}; priporočeno je 0',
    digital_zoom: 'Digitalna povečava {v}; za preslikavo območij na temperaturne podatke je potrebna 1x',
    p2p_refresh: 'Temperaturni podatki se osvežijo vsakih {v} s; za eno novo matriko na sekundo je potrebna 1 s',
    p2p_mismatch: 'Temperaturni podatki uporabljajo {v}, merilne nastavitve {e}; morata se ujemati',
    rules_enabled: 'Aktivnih merilnih pravil: {v}; priporočeno jih je 0',
    unknown: 'Za to programsko opremo še ni določeno'
  },
  profiles: {
    title: 'Profili nastavitev kamer',
    intro: 'Profil shrani nastavitve slike, tokov in merjenja obeh kamer. Referenčni profil se pred vsakim snemanjem primerja s kamerama; obnova ju vrne nanj. Omrežne nastavitve in uporabniški računi se nikoli ne spreminjajo.',
    reference: 'Referenca', useReference: 'Uporabi kot referenco', clearReference: 'Odstrani referenco', noReference: 'Ni referenčnega profila',
    empty: 'Profilov še ni. Nastavite obe kameri in tu shranite njune nastavitve.',
    saveNew: 'Shrani trenutne nastavitve', name: 'Ime profila', note: 'Opomba', makeReference: 'Uporabi kot referenco',
    restore: 'Obnovi …', restoreTitle: 'Obnovi »{n}«', restoreIntro: 'Na kameri bodo zapisane te nastavitve:',
    noChanges: 'Že enako kot v profilu.', restoreBtn: 'Obnovi nastavitve', restored: 'Obnova končana',
    remaining: 'Vrednosti, ki jih ni bilo mogoče obnoviti: {n}; glejte seznam.', deleteConfirm: 'Izbrišem profil »{n}«?',
    created: 'shranjeno {t}', changesVsRef: 'Nastavitve, drugačne od »{p}«: {n}', matchesRef: 'Ujema se z »{p}«'
  },
  settings: {
    title: 'Nastavitve',
    connections: 'Povezave s kamerami',
    connectionsHint: 'Naslov, uporabnik in geslo, s katerimi se program poveže s kamero. Pustite geslo prazno, da ostane nespremenjeno.',
    address: 'Naslov', user: 'Uporabnik', password: 'Geslo', passwordKeep: 'nespremenjeno', saveConnections: 'Shrani povezave',
    testOk: 'Povezano: {m}', testUnauthorized: 'Napačen uporabnik ali geslo', testUnreachable: 'Ni dosegljiva', testHttp: 'Kamera je odgovorila HTTP {v}',
    connectionsSaved: 'Povezave shranjene',
    numbering: 'Po vsakem snemanju',
    numberingHint: 'Izbranim poljem se po vsakem končanem snemanju poveča končna številka, npr. M-012 postane M-013. Zaporedne številke snemanj za orodje se vedno štejejo samodejno.',
    language: 'Jezik', theme: 'Videz', light: 'Svetel', dark: 'Temen',
    backup: 'Celotna varnostna kopija kamere',
    backupHint: 'Lastna celotna varnostna kopija kamere, za skrbnike. Obnovi se lahko le na spletni strani kamere.',
    download: 'Prenesi', system: 'Sistem', configFile: 'Konfiguracijska datoteka', dataDir: 'Mapa s podatki', ffmpeg: 'FFmpeg',
    simulation: 'Simulacija'
  },
  about: {
    title: 'O programu',
    text: 'Aid4SME Dashboard zajema sinhronizirane optične in termalne posnetke, radiometrične temperaturne podatke in procesne parametre celice za brizganje plastike, za strojno učenje.',
    partners: 'Razvil iThermAI v sodelovanju z Elvez.',
    funding: 'Delo je podprl projekt AID4SME, ki ga financira Evropska unija v okviru programa Obzorje Evropa, sporazum o dodelitvi sredstev št. 101189562.',
    version: 'Različica {v}', license: 'Lastniška programska oprema podjetij iThermAI in Elvez. Vse pravice pridržane.'
  },
  blocker: {
    missing_fields: 'Vnesite: {f}.', camera_checking: 'Preverjanje: {c} …', camera_offline: '{c} ({ip}) se ne odziva.',
    camera_auth: '{c} ({ip}) je zavrnila uporabniško ime ali geslo. Prijave so začasno ustavljene, da se račun ne zaklene; popravite podatke v Nastavitvah in pritisnite Preizkusi.',
    disk_low: 'Na disku za podatke je le {free} GB prostora; potrebno je {need} GB.', ffmpeg_missing: 'FFmpeg ni najden ({path}).'
  },
  warning: {
    clock_drift: 'Ura za {c} odstopa {v} s od računalnika za zajem.', settings_changed: '{c}: nastavitev, drugačnih od referenčnega profila: {n}.',
    settings_not_recommended: '{c}: nastavitev, drugačnih od priporočil: {n}.', no_reference: 'Referenčni profil kamer še ni izbran.',
    no_regions: 'Ni narisanih območij.', no_cad: '3D model izdelka ni naložen.',
    keyence_offline: 'Keyence IV3 ({ip}) se ne odziva; slike tega snemanja bodo manjkale.'
  },
  error: {
    busy_recording: 'Med snemanjem ni mogoče.', previews_paused: 'Predogledi so med snemanjem ustavljeni.',
    blocked: 'Snemanja še ni mogoče začeti; glejte seznam nad gumbom.', not_recording: 'Snemanje ne teče.',
    start_failed: 'Snemanja ni bilo mogoče začeti: {d}', invalid_name: 'Uporabite 1–32 znakov, brez < ali >.',
    name_not_supported: 'Ta kamera nima nastavitve imena kanala.', name_required: 'Vnesite ime.',
    invalid_address: 'Vnesite naslov IP ali ime gostitelja, npr. 192.168.1.30.', user_required: 'Vnesite uporabniško ime.',
    invalid_duration: 'Vnesite trajanje v minutah.', not_glb: 'To ni binarna datoteka glTF (.glb).',
    camera_offline: '{d} se ne odziva.', not_found: 'Ni najdeno.',
    cannot_open_folder: 'Mape na računalniku za zajem ni bilo mogoče odpreti: {d}', ffc_not_configured: 'Kalibracija zaklopa ni nastavljena.',
    generic: 'Prišlo je do napake: {d}'
  }
}

const messages = { en, sl }

function lookup (dict, key) {
  return key.split('.').reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), dict)
}

export function t (key, params) {
  let s = lookup(messages[locale.value], key)
  if (s === undefined) s = lookup(en, key)
  if (typeof s !== 'string') return key
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined && params[k] !== null ? params[k] : m))
  return s
}

export function camName (id) {
  const m = /(\d+)$/.exec(id || '')
  return m ? t('stream.camera', { n: m[1] }) : id
}

export function streamLabel (name) {
  if (!name) return ''
  if (name === 'keyence') return t('stream.keyence')
  const m = /^cam(\d+)_(optical|thermal|radiometric)$/.exec(name)
  if (!m) return name
  const cam = t('stream.camera', { n: m[1] })
  return locale.value === 'sl' ? `${cam} – ${t('stream.' + m[2])}` : `${cam} ${t('stream.' + m[2])}`
}

function fieldList (fields) {
  const names = fields.map((f) => t('field.' + f).toLowerCase())
  if (names.length < 2) return names.join('')
  const and = locale.value === 'sl' ? ' in ' : ' and '
  return names.slice(0, -1).join(', ') + and + names[names.length - 1]
}

export function blockerText (b) {
  if (b.code === 'missing_fields') return t('blocker.missing_fields', { f: fieldList(b.fields) })
  return t('blocker.' + b.code, { c: camName(b.camera), ip: b.ip, free: b.free, need: b.need, path: b.path })
}

export function warningText (w) {
  const v = w.value !== undefined ? (w.value > 0 ? '+' : '') + w.value : ''
  return t('warning.' + w.code, { c: camName(w.camera), n: w.count, v })
}

export function checkText (c) {
  if (c.status === 'unknown') return t('check.unknown')
  const v = c.value === null || c.value === undefined ? '–' : c.value
  return t('check.' + c.id, { v, e: c.expected === undefined ? '' : c.expected })
}

export function errorText (e) {
  const raw = (e && e.message) || String(e)
  const [code, ...rest] = raw.split(':')
  const detail = rest.join(':').trim()
  const key = 'error.' + code.trim()
  const msg = t(key, { d: detail ? camName(detail) || detail : '' })
  return msg === key ? t('error.generic', { d: raw }) : msg
}

export function eventText (e) {
  const s = t('event.' + e.type)
  return s === 'event.' + e.type ? e.type.replace(/_/g, ' ') : s
}

export function stopReasonText (r) {
  if (!r) return ''
  const s = t('stopReason.' + r)
  return s === 'stopReason.' + r ? r : s
}
