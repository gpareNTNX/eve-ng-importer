const $ = s => document.querySelector(s);
let uploadId = null;
let analysis = null;
let templates = [];
let systemState = null;
let lastJob = null;

const I18N = {
  fr: {
    'header.subtitle': 'Smart Import pour EVE-NG',
    'health.disconnected': 'Non connecté',
    'health.notDetected': 'EVE-NG non détecté',
    'health.denied': 'Connexion refusée',
    'auth.title': '1. Connexion',
    'auth.tokenPlaceholder': 'Jeton affiché par install.sh',
    'auth.connect': 'Connecter',
    'source.title': '2. Image source',
    'source.drop': 'Dépose ton fichier ici',
    'source.pick': 'Choisir un fichier',
    'source.connectFirst': 'Connecte-toi d’abord avec le jeton.',
    'source.preparing': 'Préparation de {name} ({size})',
    'source.upload': 'Upload : {percent}% • {done} / {total}',
    'source.finished': 'Upload terminé • SHA-256 {sha}… • Smart Analyse en cours',
    'common.error': 'Erreur : {message}',
    'common.missing': 'introuvable',
    'analysis.title': '3. Analyse',
    'analysis.badge': 'Analyse',
    'analysis.smartReady': 'Smart plan prêt',
    'analysis.manualMode': 'Mode manuel',
    'analysis.recognizedFiles': 'Fichiers reconnus dans la source',
    'analysis.typeFormat': 'Type : {kind} • format : {format}',
    'smart.recommended': 'SMART IMPORT RECOMMANDÉ',
    'smart.autoDetection': 'détection automatique',
    'smart.autoDetectionOnly': 'Détection automatique',
    'smart.template': 'Template EVE',
    'smart.version': 'Version',
    'smart.folder': 'Dossier cible',
    'smart.state': 'État',
    'smart.exists': 'Existe déjà',
    'smart.newImage': 'Nouvelle image',
    'smart.diskPlan': 'Plan des disques',
    'smart.blankDisk': 'Disque vierge {size} Go',
    'smart.generated': 'généré',
    'smart.copy': 'copie',
    'smart.conversion': 'conversion',
    'smart.noMapping': 'Aucun mapping disque.',
    'smart.existing': 'Déjà présents : {items}',
    'smart.why': 'Pourquoi ce choix?',
    'install.title': '4. Installation EVE-NG',
    'install.useSmart': 'Utiliser le plan Smart Import complet',
    'install.smartHelp': 'Tous les disques détectés seront installés ensemble avec les noms attendus par EVE-NG.',
    'install.template': 'Template EVE-NG',
    'install.versionName': 'Version / nom',
    'install.versionPlaceholder': 'ex. 17.12.1',
    'install.diskName': 'Nom du disque',
    'install.isoSize': 'Taille disque ISO (Go)',
    'install.targetName': 'Nom cible (optionnel)',
    'install.targetPlaceholder': "Conserver le nom d'origine",
    'install.backup': 'Sauvegarder la version existante',
    'install.dryRun': "Dry-run d'abord (recommandé)",
    'install.launchSmart': 'Lancer le Smart Import',
    'install.launch': "Lancer l’installation",
    'install.launchManual': "Lancer l’installation manuelle",
    'job.title': '5. Exécution',
    'job.waiting': 'En attente',
    'job.running': 'En cours',
    'job.done': 'Terminé',
    'job.error': 'Erreur',
    'job.drySuccess': '{kind} : dry-run réussi. Vérifie le plan, décoche « Dry-run », puis relance.',
    'job.success': '{kind} terminé. L’image est prête dans EVE-NG.',
    'system.summary': 'Templates : {templates} • qemu-img : {qemu} • images QEMU : {images} • libre : {free}',
  },
  en: {
    'header.subtitle': 'Smart Import for EVE-NG',
    'health.disconnected': 'Not connected',
    'health.notDetected': 'EVE-NG not detected',
    'health.denied': 'Connection refused',
    'auth.title': '1. Connection',
    'auth.tokenPlaceholder': 'Token displayed by install.sh',
    'auth.connect': 'Connect',
    'source.title': '2. Source image',
    'source.drop': 'Drop your file here',
    'source.pick': 'Choose a file',
    'source.connectFirst': 'Connect first using the access token.',
    'source.preparing': 'Preparing {name} ({size})',
    'source.upload': 'Upload: {percent}% • {done} / {total}',
    'source.finished': 'Upload complete • SHA-256 {sha}… • Smart Analysis in progress',
    'common.error': 'Error: {message}',
    'common.missing': 'not found',
    'analysis.title': '3. Analysis',
    'analysis.badge': 'Analysis',
    'analysis.smartReady': 'Smart plan ready',
    'analysis.manualMode': 'Manual mode',
    'analysis.recognizedFiles': 'Recognized files in the source',
    'analysis.typeFormat': 'Type: {kind} • format: {format}',
    'smart.recommended': 'RECOMMENDED SMART IMPORT',
    'smart.autoDetection': 'automatic detection',
    'smart.autoDetectionOnly': 'Automatic detection',
    'smart.template': 'EVE template',
    'smart.version': 'Version',
    'smart.folder': 'Target folder',
    'smart.state': 'State',
    'smart.exists': 'Already exists',
    'smart.newImage': 'New image',
    'smart.diskPlan': 'Disk plan',
    'smart.blankDisk': 'Blank disk {size} GB',
    'smart.generated': 'generated',
    'smart.copy': 'copy',
    'smart.conversion': 'conversion',
    'smart.noMapping': 'No disk mapping.',
    'smart.existing': 'Already installed: {items}',
    'smart.why': 'Why this choice?',
    'install.title': '4. EVE-NG installation',
    'install.useSmart': 'Use the complete Smart Import plan',
    'install.smartHelp': 'All detected disks will be installed together using the names expected by EVE-NG.',
    'install.template': 'EVE-NG template',
    'install.versionName': 'Version / name',
    'install.versionPlaceholder': 'e.g. 17.12.1',
    'install.diskName': 'Disk name',
    'install.isoSize': 'ISO disk size (GB)',
    'install.targetName': 'Target name (optional)',
    'install.targetPlaceholder': 'Keep the original name',
    'install.backup': 'Back up the existing version',
    'install.dryRun': 'Dry-run first (recommended)',
    'install.launchSmart': 'Run Smart Import',
    'install.launch': 'Start installation',
    'install.launchManual': 'Start manual installation',
    'job.title': '5. Execution',
    'job.waiting': 'Waiting',
    'job.running': 'Running',
    'job.done': 'Completed',
    'job.error': 'Error',
    'job.drySuccess': '{kind}: dry-run successful. Review the plan, uncheck “Dry-run”, then run it again.',
    'job.success': '{kind} completed. The image is ready in EVE-NG.',
    'system.summary': 'Templates: {templates} • qemu-img: {qemu} • QEMU images: {images} • free: {free}',
  }
};

function detectLanguage() {
  const saved = localStorage.getItem('eif-language');
  if (saved === 'fr' || saved === 'en') return saved;
  const browser = (navigator.languages?.[0] || navigator.language || 'en').toLowerCase();
  return browser.startsWith('fr') ? 'fr' : 'en';
}

let currentLang = detectLanguage();

function tr(key, vars = {}) {
  let value = I18N[currentLang]?.[key] ?? I18N.fr[key] ?? key;
  for (const [name, replacement] of Object.entries(vars)) {
    value = value.replaceAll(`{${name}}`, String(replacement));
  }
  return value;
}

function applyStaticTranslations() {
  document.documentElement.lang = currentLang;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = tr(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = tr(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('.langButton').forEach(btn => {
    const active = btn.dataset.lang === currentLang;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

function setLanguage(lang) {
  if (lang !== 'fr' && lang !== 'en') return;
  currentLang = lang;
  localStorage.setItem('eif-language', lang);
  applyStaticTranslations();
  if (systemState) renderSystem(systemState);
  if (analysis) showAnalysis();
  if (lastJob) renderJob(lastJob);
}

document.querySelectorAll('.langButton').forEach(btn => {
  btn.addEventListener('click', () => setLanguage(btn.dataset.lang));
});

function token() { return $('#token').value.trim(); }
function size(n) {
  const u = currentLang === 'fr' ? ['o', 'Ko', 'Mo', 'Go', 'To'] : ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
function escapeHtml(v = '') {
  return String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function backendText(value = '') {
  const text = String(value);
  if (currentLang !== 'en') return text;

  const exact = {
    'Aucune image reconnue dans le fichier/archive.': 'No recognized image was found in the file/archive.',
    'Les images IOL doivent être autorisées/licenciées pour votre environnement EVE-NG.': 'IOL images must be authorized/licensed for your EVE-NG environment.',
    "Une ISO est un média d'installation; Smart Import peut créer un disque QCOW2 vierge.": 'An ISO is installation media; Smart Import can create a blank QCOW2 disk.',
    'Smart Import ne gère pas et ne génère pas les licences IOL.': 'Smart Import does not manage or generate IOL licenses.',
    'extension .bin reconnue comme image IOL': 'the .bin extension was recognized as an IOL image',
    'extension .image reconnue comme image Dynamips': 'the .image extension was recognized as a Dynamips image',
    'Plusieurs ISO détectées; Smart Import utilise la première. Le mode manuel permet de choisir autrement.': 'Multiple ISOs were detected; Smart Import uses the first one. Manual mode lets you choose a different one.',
    'Confiance de détection faible: vérifie le template avant installation réelle.': 'Low detection confidence: verify the template before the actual installation.',
    'DRY-RUN: la cible existe; elle sera sauvegardée avant remplacement': 'DRY-RUN: the target exists; it will be backed up before replacement',
    'Plan de disques Smart Import invalide': 'Invalid Smart Import disk plan',
    'Trop de disques dans le plan Smart Import': 'Too many disks in the Smart Import plan',
    "Le média CD-ROM Smart Import n'est pas une ISO": 'The Smart Import CD-ROM media is not an ISO',
    'Plan Smart Import QEMU vide': 'Empty QEMU Smart Import plan',
    'qemu-img est requis pour convertir ce format vers qcow2': 'qemu-img is required to convert this format to qcow2',
    'qemu-img est requis pour créer les disques additionnels': 'qemu-img is required to create additional disks',
    'Candidat invalide': 'Invalid candidate',
    'Format candidat non supporté': 'Unsupported candidate format',
    'Upload inconnu': 'Unknown upload',
    'Upload introuvable': 'Upload not found',
    'JSON invalide': 'Invalid JSON',
    'Jeton invalide': 'Invalid token',
  };
  if (exact[text]) return exact[text];

  const replacements = [
    [/^préfixe (.+) trouvé$/, 'prefix $1 found'],
    [/^signature «(.+)» trouvée$/, 'signature “$1” found'],
    [/^template EVE «(.+)» correspond$/, 'EVE template “$1” matches'],
    [/^mots du template EVE: (.+)$/, 'EVE template keywords: $1'],
    [/^aucune signature produit suffisamment précise$/, 'no sufficiently precise product signature'],
    [/^layout disque: (.+)$/, 'disk layout: $1'],
    [/^Ce template utilise souvent plusieurs disques; non fournis: (.+)$/, 'This template often uses multiple disks; not provided: $1'],
    [/^Le template «(.+)» n'est pas présent dans les templates QEMU détectés sur ce serveur EVE-NG\.$/, 'The “$1” template is not present in the QEMU templates detected on this EVE-NG server.'],
    [/^La cible (.+) existe déjà; une sauvegarde sera requise avant remplacement\.$/, 'Target $1 already exists; a backup will be required before replacement.'],
    [/^Trop de disques pour une appliance EVE-NG$/, 'Too many disks for an EVE-NG appliance'],
    [/^Offset invalide: reçu (.+), attendu (.+)$/, 'Invalid offset: received $1, expected $2'],
    [/^Upload incomplet: (.+) \/ (.+) octets$/, 'Incomplete upload: $1 / $2 bytes'],
    [/^Archive non sécuritaire \(path traversal\): (.+)$/, 'Unsafe archive (path traversal): $1'],
    [/^fixpermissions introuvable: (.+)$/, 'fixpermissions not found: $1'],
    [/^Nom de disque EVE invalide\/dupliqué: (.+)$/, 'Invalid/duplicate EVE disk name: $1'],
    [/^Source Smart Import non QEMU: (.+)$/, 'Non-QEMU Smart Import source: $1'],
    [/^Nom de disque généré invalide\/dupliqué: (.+)$/, 'Invalid/duplicate generated disk name: $1'],
    [/^Le dossier cible existe déjà: (.+)$/, 'The target folder already exists: $1'],
    [/^Nom de disque EVE invalide\. Ex: (.+)$/, 'Invalid EVE disk name. Example: $1'],
    [/^Le fichier cible existe déjà: (.+)$/, 'The target file already exists: $1'],
    [/^Type non supporté: (.+)$/, 'Unsupported type: $1'],
    [/^Sauvegarde de (.+) -> (.+)$/, 'Backing up $1 -> $2'],
    [/^Cible: (.+)$/, 'Target: $1'],
    [/^Type détecté: (.+)$/, 'Detected type: $1'],
    [/^Préparation (.+) -> (.+)$/, 'Preparing $1 -> $2'],
    [/^DRY-RUN: copier: (.+) -> (.+)$/, 'DRY-RUN: copy: $1 -> $2'],
    [/^DRY-RUN: convertir (.+) -> qcow2: (.+) -> (.+)$/, 'DRY-RUN: convert $1 -> qcow2: $2 -> $3'],
    [/^DRY-RUN: créer disque vierge (.+) \((.+)G\)$/, 'DRY-RUN: create blank disk $1 ($2 GB)'],
    [/^DRY-RUN: copier (.+) -> cdrom\.iso$/, 'DRY-RUN: copy $1 -> cdrom.iso'],
    [/^DRY-RUN: copier IOL -> (.+) et rendre exécutable$/, 'DRY-RUN: copy IOL -> $1 and make it executable'],
    [/^DRY-RUN: copier Dynamips -> (.+)$/, 'DRY-RUN: copy Dynamips -> $1'],
    [/^ERREUR: (.+)$/, 'ERROR: $1'],
    [/^Paramètre invalide: (.+)$/, 'Invalid parameter: $1'],
  ];

  for (const [pattern, replacement] of replacements) {
    if (pattern.test(text)) return text.replace(pattern, replacement);
  }
  return text;
}

async function api(path, options = {}) {
  options.headers = { ...(options.headers || {}), 'X-EIF-Token': token() };
  const r = await fetch(path, options);
  let d = {};
  try { d = await r.json(); } catch {}
  if (!r.ok) throw new Error(backendText(d.error || `HTTP ${r.status}`));
  return d;
}
function status(text, cls = 'neutral') {
  $('#health').textContent = text;
  $('#health').className = `pill ${cls}`;
}
function renderSystem(s) {
  status(s.eve_detected ? `EVE-NG • v${s.version}` : tr('health.notDetected'), s.eve_detected ? 'good' : 'bad');
  $('#system').textContent = tr('system.summary', {
    templates: s.template_dir || '—',
    qemu: s.qemu_img || tr('common.missing'),
    images: s.installed_qemu_images ?? '—',
    free: size(s.free_bytes),
  });
}

$('#connect').onclick = async () => {
  try {
    sessionStorage.setItem('eif-token', token());
    systemState = await api('/api/status');
    renderSystem(systemState);
    const t = await api('/api/templates');
    templates = t.templates || [];
    fillTemplates();
  } catch (e) {
    status(tr('health.denied'), 'bad');
    $('#system').textContent = backendText(e.message);
  }
};
window.addEventListener('load', () => {
  applyStaticTranslations();
  const t = sessionStorage.getItem('eif-token');
  if (t) { $('#token').value = t; $('#connect').click(); }
});

function fillTemplates() {
  const s = $('#template');
  s.innerHTML = '';
  for (const t of templates) {
    const o = document.createElement('option');
    o.value = t.prefix;
    o.textContent = `${t.name} (${t.prefix}-*)`;
    o.dataset.disk = t.default_disk;
    s.appendChild(o);
  }
  if (!templates.length) {
    for (const p of ['newimage', 'linux', 'asav', 'vios', 'viosl2', 'nxosv9k', 'fortinet', 'paloalto']) s.add(new Option(p, p));
  }
  s.onchange = () => {
    const o = s.selectedOptions[0];
    if (o?.dataset.disk) $('#diskName').value = o.dataset.disk;
  };
}

const drop = $('#drop'), file = $('#file');
$('#pick').onclick = () => file.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('drag'); };
drop.ondragleave = () => drop.classList.remove('drag');
drop.ondrop = e => {
  e.preventDefault(); drop.classList.remove('drag');
  if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
};
file.onchange = () => file.files[0] && upload(file.files[0]);

async function upload(f) {
  try {
    if (!token()) throw new Error(tr('source.connectFirst'));
    $('#uploadBar').style.width = '0%';
    $('#uploadText').textContent = tr('source.preparing', {name: f.name, size: size(f.size)});
    const init = await api('/api/uploads/init', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({filename:f.name, size:f.size})
    });
    uploadId = init.upload_id;
    const chunk = 8 * 1024 * 1024;
    let off = 0;
    while (off < f.size) {
      const body = f.slice(off, Math.min(off + chunk, f.size));
      await api(`/api/uploads/${uploadId}/chunk`, {
        method:'PUT', headers:{'Content-Type':'application/octet-stream','X-Offset':String(off)}, body
      });
      off += body.size;
      const percent = Math.floor(off / f.size * 100);
      $('#uploadBar').style.width = `${off / f.size * 100}%`;
      $('#uploadText').textContent = tr('source.upload', {percent, done: size(off), total: size(f.size)});
    }
    const fin = await api(`/api/uploads/${uploadId}/finish`, {method:'POST'});
    $('#uploadText').textContent = tr('source.finished', {sha: fin.sha256.slice(0,16)});
    analysis = await api('/api/analyze', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({upload_id:uploadId})
    });
    showAnalysis();
  } catch (e) {
    $('#uploadText').textContent = tr('common.error', {message: backendText(e.message)});
  }
}

function confidenceClass(v) { return v >= 80 ? 'good' : v >= 60 ? 'warn' : 'bad'; }
function renderSmart(plan) {
  const panel = $('#smartPanel');
  if (!plan) { panel.hidden = true; $('#smartModeWrap').hidden = true; return; }
  panel.hidden = false;
  const conf = plan.confidence ?? 0;
  $('#smartConfidence').textContent = `${conf}%`;
  $('#smartConfidence').className = `confidence ${confidenceClass(conf)}`;
  $('#smartProduct').textContent = plan.product || plan.mode.toUpperCase();
  $('#smartVendor').textContent = plan.vendor ? `${plan.vendor} • ${tr('smart.autoDetection')}` : tr('smart.autoDetectionOnly');
  $('#smartTemplate').textContent = plan.template ? `${plan.template}-*${plan.template_available ? '' : ' ⚠'}` : plan.mode;
  $('#smartVersion').textContent = plan.version || '—';
  $('#smartFolder').textContent = plan.folder || plan.target_dir || '—';
  $('#smartTargetState').textContent = plan.target_exists ? tr('smart.exists') : tr('smart.newImage');
  $('#smartTargetState').className = plan.target_exists ? 'textWarn' : 'textGood';

  const disks = [];
  for (const d of plan.disks || []) {
    const action = d.action === 'convert' ? tr('smart.conversion') : tr('smart.copy');
    disks.push(`<div class="diskRow"><span>${escapeHtml(d.source_name)}</span><b>→</b><strong>${escapeHtml(d.disk_name)}</strong><em>${action}</em></div>`);
  }
  for (const d of plan.generated_disks || []) {
    disks.push(`<div class="diskRow generated"><span>${escapeHtml(tr('smart.blankDisk', {size:d.size_gb}))}</span><b>→</b><strong>${escapeHtml(d.disk_name)}</strong><em>${tr('smart.generated')}</em></div>`);
  }
  if (plan.cdrom_relpath) {
    disks.push(`<div class="diskRow"><span>${escapeHtml(plan.cdrom_relpath.split('/').pop())}</span><b>→</b><strong>cdrom.iso</strong><em>ISO</em></div>`);
  }
  $('#smartDisks').innerHTML = disks.join('') || `<div class="small muted">${tr('smart.noMapping')}</div>`;
  $('#smartExisting').textContent = (plan.existing_versions || []).length ? tr('smart.existing', {items:plan.existing_versions.join(', ')}) : '';
  $('#smartWarnings').innerHTML = (plan.warnings || []).map(w => `<div class="warning">${escapeHtml(backendText(w))}</div>`).join('');
  $('#smartReasons').innerHTML = (plan.reasons || []).map(r => `<div>• ${escapeHtml(backendText(r))}</div>`).join('');

  const smartQemu = plan.mode === 'qemu';
  $('#smartModeWrap').hidden = !smartQemu;
  $('#smartMode').checked = smartQemu;
  toggleMode();
}

function showAnalysis() {
  const c = $('#candidate');
  const selected = c.value;
  c.innerHTML = '';
  for (const x of analysis.candidates) {
    const o = new Option(`${x.kind.toUpperCase()} • ${x.relpath} • ${size(x.size)}`, x.relpath);
    o.dataset.kind = x.kind;
    o.dataset.format = x.format;
    c.add(o);
  }
  if (selected && [...c.options].some(o => o.value === selected)) c.value = selected;
  $('#warnings').innerHTML = (analysis.warnings || []).map(w => `<div class="warning">${escapeHtml(backendText(w))}</div>`).join('');
  $('#analysisCard').hidden = false;
  $('#installCard').hidden = !analysis.candidates.length;
  $('#analysisBadge').textContent = analysis.smart_plan ? tr('analysis.smartReady') : tr('analysis.manualMode');
  $('#analysisBadge').className = `pill ${analysis.smart_plan ? 'good' : 'neutral'}`;
  renderSmart(analysis.smart_plan);
  c.onchange = updateCandidate;
  updateCandidate();
}

function updateCandidate() {
  const o = $('#candidate').selectedOptions[0];
  if (!o) return;
  const kind = o.dataset.kind;
  $('#candidateInfo').textContent = tr('analysis.typeFormat', {kind, format:o.dataset.format});
  if ($('#smartMode').checked && analysis?.smart_plan?.mode === 'qemu') return;
  const q = kind === 'qemu' || kind === 'qemu-iso';
  $('#qemuFields').hidden = !q;
  $('#simpleFields').hidden = q;
  $('#isoSizeWrap').hidden = kind !== 'qemu-iso';
  if (q && $('#template').selectedOptions[0]?.dataset.disk) $('#diskName').value = $('#template').selectedOptions[0].dataset.disk;
  $('#install').textContent = tr('install.launch');
}

function toggleMode() {
  const smart = $('#smartMode').checked && analysis?.smart_plan?.mode === 'qemu';
  $('#manualPanel').hidden = smart;
  $('#install').textContent = smart ? tr('install.launchSmart') : tr('install.launchManual');
  if (!smart) updateCandidate();
}
$('#smartMode').onchange = toggleMode;

function buildInstallSpec() {
  const backup = $('#backup').checked;
  const dry = $('#dry').checked;
  const plan = analysis?.smart_plan;
  if ($('#smartMode').checked && plan?.mode === 'qemu') {
    return {
      upload_id: uploadId,
      smart_mode: true,
      template: plan.template,
      version: plan.version,
      disks: (plan.disks || []).map(d => ({relpath:d.relpath, disk_name:d.disk_name})),
      generated_disks: (plan.generated_disks || []).map(d => ({disk_name:d.disk_name, size_gb:d.size_gb})),
      cdrom_relpath: plan.cdrom_relpath || null,
      backup_existing: backup,
      dry_run: dry,
    };
  }

  const o = $('#candidate').selectedOptions[0];
  const kind = o.dataset.kind;
  const spec = {upload_id:uploadId, relpath:o.value, backup_existing:backup, dry_run:dry};
  if (kind === 'qemu' || kind === 'qemu-iso') {
    spec.template = $('#template').value || 'newimage';
    spec.version = $('#version').value || analysis.filename.replace(/\.[^.]+$/, '');
    spec.disk_name = $('#diskName').value;
    spec.iso_disk_size_gb = parseInt($('#isoSize').value || '20', 10);
  } else {
    spec.target_name = $('#targetName').value.trim();
  }
  return spec;
}

$('#install').onclick = async () => {
  try {
    const j = await api('/api/install', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(buildInstallSpec())
    });
    $('#jobCard').hidden = false;
    $('#result').innerHTML = '';
    poll(j.job_id);
  } catch (e) { alert(backendText(e.message)); }
};

function renderJob(j) {
  lastJob = j;
  $('#jobBar').style.width = `${j.progress || 0}%`;
  $('#logs').textContent = (j.logs || []).map(backendText).join('\n');
  $('#logs').scrollTop = $('#logs').scrollHeight;
  const statusKey = j.status === 'running' ? 'job.running' : j.status === 'done' ? 'job.done' : 'job.error';
  $('#jobStatus').textContent = tr(statusKey);
  $('#jobStatus').className = `pill ${j.status === 'done' ? 'good' : j.status === 'error' ? 'bad' : 'neutral'}`;
  if (j.status === 'done') {
    const kind = j.result?.smart_import ? 'Smart Import' : 'Installation';
    const key = j.result?.dry_run ? 'job.drySuccess' : 'job.success';
    $('#result').innerHTML = `<div class="success">${escapeHtml(tr(key, {kind}))}</div>`;
  } else if (j.status === 'error') {
    $('#result').innerHTML = `<div class="error">${escapeHtml(backendText(j.error))}</div>`;
  }
}

async function poll(jid) {
  let done = false;
  while (!done) {
    try {
      const j = await api(`/api/jobs/${jid}`);
      renderJob(j);
      done = j.status === 'done' || j.status === 'error';
    } catch (e) {
      done = true;
      $('#result').innerHTML = `<div class="error">${escapeHtml(backendText(e.message))}</div>`;
    }
    if (!done) await new Promise(r => setTimeout(r, 1000));
  }
}
