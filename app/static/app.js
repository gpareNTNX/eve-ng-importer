const $ = s => document.querySelector(s);
let uploadId = null;
let analysis = null;
let templates = [];

function token() { return $('#token').value.trim(); }
function size(n) {
  const u = ['o', 'Ko', 'Mo', 'Go', 'To'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
function escapeHtml(v = '') {
  return String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
async function api(path, options = {}) {
  options.headers = { ...(options.headers || {}), 'X-EIF-Token': token() };
  const r = await fetch(path, options);
  let d = {};
  try { d = await r.json(); } catch {}
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}
function status(text, cls = 'neutral') {
  $('#health').textContent = text;
  $('#health').className = `pill ${cls}`;
}

$('#connect').onclick = async () => {
  try {
    sessionStorage.setItem('eif-token', token());
    const s = await api('/api/status');
    status(s.eve_detected ? `EVE-NG • v${s.version}` : 'EVE-NG non détecté', s.eve_detected ? 'good' : 'bad');
    $('#system').textContent = `Templates: ${s.template_dir || '—'} • qemu-img: ${s.qemu_img || 'introuvable'} • images QEMU: ${s.installed_qemu_images ?? '—'} • libre: ${size(s.free_bytes)}`;
    const t = await api('/api/templates');
    templates = t.templates || [];
    fillTemplates();
  } catch (e) {
    status('Connexion refusée', 'bad');
    $('#system').textContent = e.message;
  }
};
window.addEventListener('load', () => {
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
    if (!token()) throw new Error('Connecte-toi d’abord avec le jeton.');
    $('#uploadBar').style.width = '0%';
    $('#uploadText').textContent = `Préparation de ${f.name} (${size(f.size)})`;
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
      $('#uploadBar').style.width = `${off / f.size * 100}%`;
      $('#uploadText').textContent = `Upload: ${Math.floor(off / f.size * 100)}% • ${size(off)} / ${size(f.size)}`;
    }
    const fin = await api(`/api/uploads/${uploadId}/finish`, {method:'POST'});
    $('#uploadText').textContent = `Upload terminé • SHA-256 ${fin.sha256.slice(0,16)}… • Smart Analyse en cours`;
    analysis = await api('/api/analyze', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({upload_id:uploadId})
    });
    showAnalysis();
  } catch (e) {
    $('#uploadText').textContent = `Erreur: ${e.message}`;
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
  $('#smartVendor').textContent = plan.vendor ? `${plan.vendor} • détection automatique` : 'Détection automatique';
  $('#smartTemplate').textContent = plan.template ? `${plan.template}-*${plan.template_available ? '' : ' ⚠'}` : plan.mode;
  $('#smartVersion').textContent = plan.version || '—';
  $('#smartFolder').textContent = plan.folder || plan.target_dir || '—';
  $('#smartTargetState').textContent = plan.target_exists ? 'Existe déjà' : 'Nouvelle image';
  $('#smartTargetState').className = plan.target_exists ? 'textWarn' : 'textGood';

  const disks = [];
  for (const d of plan.disks || []) {
    disks.push(`<div class="diskRow"><span>${escapeHtml(d.source_name)}</span><b>→</b><strong>${escapeHtml(d.disk_name)}</strong><em>${d.action === 'convert' ? 'conversion' : 'copie'}</em></div>`);
  }
  for (const d of plan.generated_disks || []) {
    disks.push(`<div class="diskRow generated"><span>Disque vierge ${d.size_gb} Go</span><b>→</b><strong>${escapeHtml(d.disk_name)}</strong><em>généré</em></div>`);
  }
  if (plan.cdrom_relpath) {
    disks.push(`<div class="diskRow"><span>${escapeHtml(plan.cdrom_relpath.split('/').pop())}</span><b>→</b><strong>cdrom.iso</strong><em>ISO</em></div>`);
  }
  $('#smartDisks').innerHTML = disks.join('') || '<div class="small muted">Aucun mapping disque.</div>';
  $('#smartExisting').textContent = (plan.existing_versions || []).length ? `Déjà présents: ${plan.existing_versions.join(', ')}` : '';
  $('#smartWarnings').innerHTML = (plan.warnings || []).map(w => `<div class="warning">${escapeHtml(w)}</div>`).join('');
  $('#smartReasons').innerHTML = (plan.reasons || []).map(r => `<div>• ${escapeHtml(r)}</div>`).join('');

  const smartQemu = plan.mode === 'qemu';
  $('#smartModeWrap').hidden = !smartQemu;
  $('#smartMode').checked = smartQemu;
  toggleMode();
}

function showAnalysis() {
  const c = $('#candidate');
  c.innerHTML = '';
  for (const x of analysis.candidates) {
    const o = new Option(`${x.kind.toUpperCase()} • ${x.relpath} • ${size(x.size)}`, x.relpath);
    o.dataset.kind = x.kind;
    o.dataset.format = x.format;
    c.add(o);
  }
  $('#warnings').innerHTML = (analysis.warnings || []).map(w => `<div class="warning">${escapeHtml(w)}</div>`).join('');
  $('#analysisCard').hidden = false;
  $('#installCard').hidden = !analysis.candidates.length;
  $('#analysisBadge').textContent = analysis.smart_plan ? 'Smart plan prêt' : 'Mode manuel';
  $('#analysisBadge').className = `pill ${analysis.smart_plan ? 'good' : 'neutral'}`;
  renderSmart(analysis.smart_plan);
  c.onchange = updateCandidate;
  updateCandidate();
}

function updateCandidate() {
  const o = $('#candidate').selectedOptions[0];
  if (!o) return;
  const kind = o.dataset.kind;
  $('#candidateInfo').textContent = `Type: ${kind} • format: ${o.dataset.format}`;
  if ($('#smartMode').checked && analysis?.smart_plan?.mode === 'qemu') return;
  const q = kind === 'qemu' || kind === 'qemu-iso';
  $('#qemuFields').hidden = !q;
  $('#simpleFields').hidden = q;
  $('#isoSizeWrap').hidden = kind !== 'qemu-iso';
  if (q && $('#template').selectedOptions[0]?.dataset.disk) $('#diskName').value = $('#template').selectedOptions[0].dataset.disk;
  $('#install').textContent = 'Lancer l’installation';
}

function toggleMode() {
  const smart = $('#smartMode').checked && analysis?.smart_plan?.mode === 'qemu';
  $('#manualPanel').hidden = smart;
  $('#install').textContent = smart ? 'Lancer le Smart Import' : 'Lancer l’installation manuelle';
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
  } catch (e) { alert(e.message); }
};

async function poll(jid) {
  let done = false;
  while (!done) {
    try {
      const j = await api(`/api/jobs/${jid}`);
      $('#jobBar').style.width = `${j.progress || 0}%`;
      $('#logs').textContent = (j.logs || []).join('\n');
      $('#logs').scrollTop = $('#logs').scrollHeight;
      $('#jobStatus').textContent = j.status === 'running' ? 'En cours' : j.status === 'done' ? 'Terminé' : 'Erreur';
      $('#jobStatus').className = `pill ${j.status === 'done' ? 'good' : j.status === 'error' ? 'bad' : 'neutral'}`;
      if (j.status === 'done') {
        done = true;
        const smart = j.result?.smart_import ? 'Smart Import' : 'Installation';
        $('#result').innerHTML = `<div class="success">${j.result?.dry_run ? `${smart}: dry-run réussi. Vérifie le plan, décoche « Dry-run », puis relance.` : `${smart} terminé. L’image est prête dans EVE-NG.`}</div>`;
      }
      if (j.status === 'error') {
        done = true;
        $('#result').innerHTML = `<div class="error">${escapeHtml(j.error)}</div>`;
      }
    } catch (e) {
      done = true;
      $('#result').innerHTML = `<div class="error">${escapeHtml(e.message)}</div>`;
    }
    if (!done) await new Promise(r => setTimeout(r, 1000));
  }
}
