/* ── API client ── */
const API = {
  get:  (url)      => {
    const bust = url.includes('?') ? `&_t=${Date.now()}` : `?_t=${Date.now()}`;
    return fetch(url + bust, { cache: 'no-store' }).then(r => r.ok ? r.json() : r.json().then(e => {throw e})).catch(err => { toast(err.error || 'Erro de conexão', 'err'); throw err; });
  },
  post: (url, d, timeoutMs = 0) => {
    const opts = {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(d)};
    if (timeoutMs > 0) {
      const ctrl = new AbortController();
      opts.signal = ctrl.signal;
      setTimeout(() => ctrl.abort(), timeoutMs);
    }
    return fetch(url, opts)
      .then(r => r.ok ? r.json() : r.json().then(e => {throw e}))
      .catch(err => {
        if (err.name === 'AbortError') { toast('Tempo limite excedido. Tente novamente.', 'err'); throw err; }
        toast(err.error || 'Erro ao salvar', 'err');
        throw err;
      });
  },
  put:  (url, d)   => fetch(url, {method:'PUT',   headers:{'Content-Type':'application/json'}, body:JSON.stringify(d)}).then(r => r.ok ? r.json() : r.json().then(e => {throw e})).catch(err => { toast(err.error || 'Erro ao atualizar', 'err'); throw err; }),
  del:  (url)      => fetch(url, {method:'DELETE'}).then(r => r.ok ? r.json() : r.json().then(e => {throw e})).catch(err => { toast(err.error || 'Erro ao remover', 'err'); throw err; }),
};

/* ── Toast ── */
let toastTimer;
function toast(msg, type='') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (type ? ' '+type : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className='', 2500);
}

/* ── Router ── */
function go(hash) { location.hash = hash; }

window.addEventListener('hashchange', route);
window.addEventListener('load', route);

function route() {
  const h = location.hash.slice(1) || '/';
  const app = document.getElementById('app');

  stopCamera();

  const m = (re) => h.match(re);
  let r;

  if (h === '/')                              return renderHome(app);
  if (h === '/aircrafts')                     return renderAircraftList(app);
  if (h === '/aircraft/new')                  return renderNewAircraft(app);
  if (h === '/area/new')                      return renderNewArea(app);
  if ((r = m(/^\/aircraft\/(\d+)$/)))         return renderAircraftDetail(app, r[1]);
  if ((r = m(/^\/area\/(\d+)\/mask$/)))       return renderMaskEditor(app, r[1]);
  // Position routes (new)
  if ((r = m(/^\/aircraft\/(\d+)\/pos\/([A-Z0-9]+)$/)))                                    return renderPositionDetail(app, r[1], r[2]);
  if ((r = m(/^\/aircraft\/(\d+)\/pos\/([A-Z0-9]+)\/group\/(\d+)$/)))                      return renderGroupDetail(app, r[1], r[2], r[3]);
  if ((r = m(/^\/aircraft\/(\d+)\/pos\/([A-Z0-9]+)\/area\/(\d+)$/)))                       return renderAreaDetail(app, r[3], r[1], r[2]);
  if ((r = m(/^\/aircraft\/(\d+)\/pos\/([A-Z0-9]+)\/area\/(\d+)\/(before|after)\/view$/))) return renderPhotoViewer(app, r[1], r[3], r[4], r[2]);
  if ((r = m(/^\/aircraft\/(\d+)\/pos\/([A-Z0-9]+)\/area\/(\d+)\/(before|after)$/)))       return renderCapture(app, r[1], r[3], r[4], r[2]);
  // Legacy routes
  if ((r = m(/^\/aircraft\/(\d+)\/area\/(\d+)$/)))                   return renderAreaDetail(app, r[2], r[1], null);
  if ((r = m(/^\/area\/(\d+)$/)))                                    return renderAreaDetail(app, r[1], null, null);
  if ((r = m(/^\/aircraft\/(\d+)\/area\/(\d+)\/(before|after)$/)))   return renderCapture(app, r[1], r[2], r[3], null);
  if ((r = m(/^\/analysis\/(\d+)$/)))         return renderAnalysisResult(app, r[1]);
  if ((r = m(/^\/feedback\/(\d+)$/)))         return renderFeedback(app, r[1]);
  go('/');
}

/* ════════════════════════════════════════════
   HOME — Lista de aeronaves + Modelos Globais
════════════════════════════════════════════ */
function getPhase() {
  return localStorage.getItem('phase') || 'Recebimento';
}

function setPhase(phase) {
  localStorage.setItem('phase', phase);
  go('/aircrafts');
}

function toggleIffMenu() {
  const menu = document.getElementById('iff-menu');
  menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

async function renderHome(app) {
  app.innerHTML = `
    <div class="app-header">
      <a class="header-logo" href="#/">
        <img src="/static/embraer-logo.svg" alt="Embraer">
      </a>
      <div class="header-logo-divider"></div>
      <h1>Gestão de Inspeção Visual</h1>
    </div>
    <div class="view" style="display:flex;flex-direction:column;gap:16px;padding-top:24px;">
      
      <div class="card" onclick="setPhase('Recebimento')" style="padding:16px;align-items:center;">
        <img src="/static/icons/icon_recebimento.png" style="width:48px;height:48px;border-radius:8px;margin-right:16px;">
        <div class="card-body">
          <div class="card-title" style="font-size:1.1rem;">Recebimento</div>
          <div class="card-sub">Inspeção de chegada</div>
        </div>
        <span style="color:var(--muted);font-size:1.5rem">›</span>
      </div>

      <div class="card" onclick="setPhase('IFP')" style="padding:16px;align-items:center;">
        <img src="/static/icons/icon_ifp.png" style="width:48px;height:48px;border-radius:8px;margin-right:16px;">
        <div class="card-body">
          <div class="card-title" style="font-size:1.1rem;">IFP</div>
          <div class="card-sub">Inspeção Final da Produção</div>
        </div>
        <span style="color:var(--muted);font-size:1.5rem">›</span>
      </div>

      <div class="card" onclick="toggleIffMenu()" style="padding:16px;align-items:center;background:var(--card-bg);">
        <img src="/static/icons/icon_iff_producao.png" style="width:48px;height:48px;border-radius:8px;margin-right:16px;">
        <div class="card-body">
          <div class="card-title" style="font-size:1.1rem;">IFF</div>
          <div class="card-sub">Inspeção Final de Fabricação</div>
        </div>
        <span style="color:var(--muted);font-size:1.5rem">▾</span>
      </div>
      
      <div id="iff-menu" style="display:none;margin-left:32px;margin-top:-8px;border-left:2px solid var(--border);padding-left:16px;display:flex;flex-direction:column;gap:8px;">
        <div class="card" onclick="setPhase('IFF - Qualidade')" style="padding:12px;background:rgba(255,255,255,0.02)">
          <img src="/static/icons/icon_iff_qualidade.png" style="width:32px;height:32px;border-radius:6px;margin-right:12px;">
          <div class="card-body"><div class="card-title">Qualidade (QA)</div></div>
        </div>
        <div class="card" onclick="setPhase('IFF - Produção')" style="padding:12px;background:rgba(255,255,255,0.02)">
          <img src="/static/icons/icon_iff_producao.png" style="width:32px;height:32px;border-radius:6px;margin-right:12px;">
          <div class="card-body"><div class="card-title">Produção</div></div>
        </div>
      </div>

    </div>
  `;
  document.getElementById('iff-menu').style.display = 'none'; // reset menu state
}

/* ════════════════════════════════════════════
   AIRCRAFT LIST — Lista de aeronaves + Modelos
════════════════════════════════════════════ */
async function renderAircraftList(app) {
  const phase = getPhase();
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('/')">‹</button>
      <a class="header-logo" href="#/">
        <img src="/static/embraer-logo.svg" alt="Embraer">
      </a>
      <div class="header-logo-divider"></div>
      <h1 style="font-size:1.1rem">${phase}</h1>
    </div>
    <div class="view">
      <div class="section-label">Aeronaves</div>
      <div id="home-aircraft" class="cards-grid"><div class="spinner"></div></div>
      <button class="btn btn-ghost" onclick="go('/aircraft/new')" style="margin-top:8px">+ Nova aeronave</button>

      <div class="divider" style="margin:24px 0"></div>

      <div class="section-label">Modelos de Máscara (Globais)</div>
      <div id="home-areas" class="cards-grid"><div class="spinner"></div></div>
      <button class="btn btn-ghost" onclick="go('/area/new')" style="margin-top:8px">+ Novo modelo global</button>
    </div>`;

  const [aircraft, areas] = await Promise.all([
    API.get('/api/aircraft').catch(() => []),
    API.get('/api/areas').catch(() => []),
  ]);

  const acList = document.getElementById('home-aircraft');
  if (!aircraft.length) {
    acList.innerHTML = `<p style="color:var(--muted);font-size:0.85rem">Nenhuma aeronave cadastrada.</p>`;
  } else {
  acList.innerHTML = aircraft.map(a => `
      <div class="card" onclick="go('/aircraft/${a.id}')">
        <span class="card-icon">🛩️</span>
        <div class="card-body">
          <div class="card-title">${esc(a.serial)}</div>
        </div>
        <span style="color:var(--muted);font-size:1.2rem">›</span>
      </div>`).join('');
  }

  const arList = document.getElementById('home-areas');
  if (!areas.length) {
    arList.innerHTML = `<p style="color:var(--muted);font-size:0.85rem">Nenhum modelo de máscara criado.</p>`;
  } else {
    arList.innerHTML = areas.map(a => `
      <div class="card" onclick="go('/area/${a.id}')">
        ${a.mask_thumb ? `<img class="card-thumb" src="${a.mask_thumb}">` : `<span class="card-icon">📐</span>`}
        <div class="card-body">
          <div class="card-title">${esc(a.name)}</div>
          <div class="card-sub">${a.mask_thumb ? '✅ Configurado' : '⚠️ Sem máscara'}</div>
        </div>
        <span style="color:var(--muted);font-size:1.2rem">›</span>
      </div>`).join('');
  }
}

/* ════════════════════════════════════════════
   NOVA AERONAVE
════════════════════════════════════════════ */
function renderNewAircraft(app) {
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="history.back()">‹</button>
      <a class="header-logo" href="#/"><img src="/static/embraer-logo.svg" alt="Embraer"></a>
      <div class="header-logo-divider"></div>
      <h1>Nova aeronave</h1>
    </div>
    <div class="view">
      <div class="form-group">
        <label class="form-label">Número de série</label>
        <input id="f-serial" class="form-input" placeholder="ex: 20227" autocapitalize="characters" inputmode="numeric">
      </div>
      <button class="btn btn-primary" onclick="submitAircraft()">Cadastrar</button>
    </div>`;
}

async function submitAircraft() {
  const serial = document.getElementById('f-serial').value.trim();
  if (!serial) { toast('Informe o número de série', 'err'); return; }
  const res = await API.post('/api/aircraft', { serial });
  if (res?.error) { toast(res.error, 'err'); return; }
  go(`/aircraft/${res.id}`);
}

/* ════════════════════════════════════════════
   DETALHE DA AERONAVE — Selecionar Área (Modelo)
════════════════════════════════════════════ */
const POSITIONS = ['P4', 'P3', 'P2', 'P1', 'P0', 'F30'];

async function renderAircraftDetail(app, id) {
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('/')">‹</button>
      <a class="header-logo" href="#/"><img src="/static/embraer-logo.svg" alt="Embraer"></a>
      <div class="header-logo-divider"></div>
      <h1 id="ac-title">…</h1>
      <button class="btn-icon" style="color:var(--danger)" onclick="deleteAircraft(${id})" title="Remover">🗑</button>
    </div>
    <div class="view">
      <div class="section-label">Posições de Inspeção</div>
      <div id="pos-grid" class="cards-grid"></div>
      <div class="btn-row" style="margin-top:24px;">
        <button class="btn btn-primary" onclick="analyzeAircraft(${id})" id="btn-analyze-aircraft">🔬 Analisar Avião</button>
        <button class="btn btn-ghost" onclick="downloadReport(${id})">📄 Relatório PDF</button>
      </div>
    </div>`;

  const aircraft = await API.get('/api/aircraft').then(list => list.find(a => a.id == id) || {});
  document.getElementById('ac-title').textContent = aircraft.serial || '—';

  document.getElementById('pos-grid').innerHTML = POSITIONS.map(pos => `
    <div class="card" onclick="go('/aircraft/${id}/pos/${pos}')">
      <span class="card-icon" style="font-size:1.1rem;font-weight:700;color:var(--accent)">${pos}</span>
      <div class="card-body">
        <div class="card-title">Posição ${pos}</div>
      </div>
      <span style="color:var(--muted);font-size:1.2rem">›</span>
    </div>`).join('');
}

async function analyzeAircraft(id) {
  const btn = document.getElementById('btn-analyze-aircraft');
  btn.disabled = true;
  btn.innerHTML = '⏳ Analisando… <small style="opacity:.7;font-size:.8rem">(pode levar até 2 min)</small>';
  try {
    const res = await API.post(`/api/aircraft/${id}/analyze`, { phase: getPhase() }, 120000);
    const ok  = res.results?.filter(r => r.status === 'OK').length || 0;
    const tot = res.results?.length || 0;
    toast(`✅ ${ok}/${tot} áreas íntegras`, 'ok');
    const damaged = res.results?.find(r => r.analysis_id && r.status !== 'OK');
    if (damaged) go(`/analysis/${damaged.analysis_id}`);
    else renderAircraftDetail(document.getElementById('app'), id);
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🔬 Analisar Avião';
  }
}

/* ════════════════════════════════════════════
   POSIÇÃO — 6 posições fixas + áreas
════════════════════════════════════════════ */
async function renderPositionDetail(app, aircraftId, position) {
  const aircraft = await API.get('/api/aircraft').then(l => l.find(a => a.id == aircraftId) || {});
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('/aircraft/${aircraftId}')">‹</button>
      <a class="header-logo" href="#/"><img src="/static/embraer-logo.svg" alt="Embraer"></a>
      <div class="header-logo-divider"></div>
      <h1>${esc(aircraft.serial)} | ${position}</h1>
    </div>
    <div class="view" style="padding-bottom: 80px">
      <div class="section-label" style="display:flex; justify-content:space-between; align-items:center">
        Áreas (Pastas)
        <button class="btn btn-ghost btn-small" onclick="createNewGroup(${aircraftId}, '${position}')" style="padding:4px 8px; font-size:0.8rem">+ Nova</button>
      </div>
      <div id="pos-groups" class="cards-grid"><div class="spinner"></div></div>
      
      <div class="section-label" style="margin-top:24px">Sub-áreas Livres</div>
      <div id="pos-areas" class="cards-grid"><div class="spinner"></div></div>
      
      <div class="btn-row" style="margin-top:20px">
        <button class="btn btn-primary" onclick="analyzePosition(${aircraftId},'${position}')" id="btn-analyze-pos">🔬 Analisar Posição</button>
        <button class="btn btn-ghost" onclick="downloadReport(${aircraftId}, '${position}')">📄 PDF</button>
      </div>
    </div>
    <div id="move-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:999; align-items:center; justify-content:center; padding:16px;">
      <div class="card" style="width:100%; max-width:400px; padding:24px; background:var(--card-bg);">
        <h3 style="margin-bottom:16px;">Mover Sub-área</h3>
        <p style="margin-bottom:12px; color:var(--muted); font-size:0.9rem" id="move-modal-text"></p>
        <select id="move-group-select" class="form-input" style="margin-bottom:16px; background:#111; color:#fff; padding:12px; width:100%; border:1px solid #333; border-radius:8px;">
        </select>
        <div style="display:flex; gap:12px">
          <button class="btn btn-ghost" onclick="closeMoveModal()" style="flex:1">Cancelar</button>
          <button class="btn btn-primary" onclick="confirmMoveSubarea()" style="flex:1">Confirmar</button>
        </div>
      </div>
    </div>`;

  const phase = getPhase();
  const [groups, posAreas, allAreas] = await Promise.all([
    API.get(`/api/aircraft/${aircraftId}/pos/${position}/groups`).catch(() => []),
    API.get(`/api/aircraft/${aircraftId}/pos/${position}/areas?phase=${encodeURIComponent(phase)}`).catch(() => []),
    API.get('/api/areas').catch(() => []),
  ]);

  window._currentPositionGroups = groups;
  window._currentAircraftId = aircraftId;
  window._currentPosition = position;

  const groupedAreaIds = new Set();
  groups.forEach(g => {
    g.subareas.forEach(sa => groupedAreaIds.add(sa.id));
  });

  const withPhotos = new Set(posAreas.map(a => a.area_id));

  // Render Groups
  const groupsGrid = document.getElementById('pos-groups');
  if (!groups.length) {
    groupsGrid.innerHTML = `<div class="no-mask-banner" style="grid-column: 1/-1;">Nenhuma área criada.</div>`;
  } else {
    groupsGrid.innerHTML = groups.map(g => `
      <div class="card" onclick="go('/aircraft/${aircraftId}/pos/${position}/group/${g.id}')">
        <span class="card-icon">📁</span>
        <div class="card-body">
          <div class="card-title">${esc(g.name)}</div>
          <div class="card-sub">${g.subareas.length} sub-áreas</div>
        </div>
        <span style="color:var(--muted);font-size:1.2rem">›</span>
      </div>`).join('');
  }

  // Render Ungrouped Areas
  const freeAreas = allAreas.filter(a => !groupedAreaIds.has(a.id));
  const grid = document.getElementById('pos-areas');
  if (!freeAreas.length) {
    grid.innerHTML = `<div class="no-mask-banner" style="grid-column: 1/-1;">Todas as sub-áreas estão agrupadas.</div>`;
  } else {
    grid.innerHTML = freeAreas.map(a => `
      <div class="card">
        <div style="display:flex; flex:1; align-items:center;" onclick="go('/aircraft/${aircraftId}/pos/${position}/area/${a.id}')">
          ${a.mask_thumb ? `<img class="card-thumb" src="${a.mask_thumb}">` : `<span class="card-icon">📐</span>`}
          <div class="card-body">
            <div class="card-title">${esc(a.name)}</div>
            <div class="card-sub">${withPhotos.has(a.id) ? '✅ Com fotos' : '📸 Sem fotos'}</div>
          </div>
        </div>
        ${groups.length > 0 ? `<button class="btn-icon" style="background:#222; padding:8px; border-radius:6px; font-size:0.8rem; margin-left:8px;" onclick="openMoveModal(${a.id}, '${esc(a.name)}')">Mover</button>` : ''}
      </div>`).join('');
  }
}

async function createNewGroup(aircraftId, position) {
  const name = prompt("Nome da Nova Área (ex: Cockpit):");
  if (!name || !name.trim()) return;
  try {
    await API.post(`/api/aircraft/${aircraftId}/pos/${position}/groups`, { name: name.trim() });
    renderPositionDetail(document.getElementById('app'), aircraftId, position);
  } catch(e) {}
}

let _moveToAreaId = null;
function openMoveModal(areaId, areaName) {
  _moveToAreaId = areaId;
  const groups = window._currentPositionGroups || [];
  document.getElementById('move-modal-text').textContent = `Selecione a área de destino para "${areaName}":`;
  const select = document.getElementById('move-group-select');
  select.innerHTML = groups.map(g => `<option value="${g.id}">${esc(g.name)}</option>`).join('');
  document.getElementById('move-modal').style.display = 'flex';
}
function closeMoveModal() {
  document.getElementById('move-modal').style.display = 'none';
  _moveToAreaId = null;
}
async function confirmMoveSubarea() {
  if (!_moveToAreaId) return;
  const groupId = document.getElementById('move-group-select').value;
  if (!groupId) return;
  try {
    await API.post(`/api/groups/${groupId}/subareas`, { area_id: _moveToAreaId });
    closeMoveModal();
    renderPositionDetail(document.getElementById('app'), window._currentAircraftId, window._currentPosition);
  } catch(e) {}
}

async function renderGroupDetail(app, aircraftId, position, groupId) {
  const phase = getPhase();
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('/aircraft/${aircraftId}/pos/${position}')">‹</button>
      <a class="header-logo" href="#/"><img src="/static/embraer-logo.svg" alt="Embraer"></a>
      <div class="header-logo-divider"></div>
      <h1>Carregando...</h1>
    </div>
    <div class="view">
      <div id="group-areas" class="cards-grid"><div class="spinner"></div></div>
    </div>`;

  const [groups, posAreas] = await Promise.all([
    API.get(`/api/aircraft/${aircraftId}/pos/${position}/groups`).catch(() => []),
    API.get(`/api/aircraft/${aircraftId}/pos/${position}/areas?phase=${encodeURIComponent(phase)}`).catch(() => []),
  ]);

  const group = groups.find(g => g.id == groupId);
  if (!group) { go(`/aircraft/${aircraftId}/pos/${position}`); return; }

  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('/aircraft/${aircraftId}/pos/${position}')">‹</button>
      <a class="header-logo" href="#/"><img src="/static/embraer-logo.svg" alt="Embraer"></a>
      <div class="header-logo-divider"></div>
      <h1>${esc(group.name)}</h1>
    </div>
    <div class="view">
      <div class="section-label">Sub-áreas em ${esc(group.name)}</div>
      <div id="group-areas" class="cards-grid"></div>
    </div>`;

  const withPhotos = new Set(posAreas.map(a => a.area_id));
  const grid = document.getElementById('group-areas');

  if (!group.subareas.length) {
    grid.innerHTML = `<div class="no-mask-banner" style="grid-column: 1/-1;">Nenhuma sub-área nesta área. Mova-as através da tela da Posição.</div>`;
  } else {
    grid.innerHTML = group.subareas.map(a => `
      <div class="card">
        <div style="display:flex; flex:1; align-items:center;" onclick="go('/aircraft/${aircraftId}/pos/${position}/area/${a.id}')">
          ${a.mask_thumb ? `<img class="card-thumb" src="${a.mask_thumb}">` : `<span class="card-icon">📐</span>`}
          <div class="card-body">
            <div class="card-title">${esc(a.name)}</div>
            <div class="card-sub">${withPhotos.has(a.id) ? '✅ Com fotos' : '📸 Sem fotos'}</div>
          </div>
        </div>
        <button class="btn-icon" style="background:var(--danger); color:#fff; padding:8px; border-radius:6px; font-size:0.8rem; margin-left:8px;" onclick="removeSubareaFromGroup(${groupId}, ${a.id})">Remover</button>
      </div>`).join('');
  }
}

async function removeSubareaFromGroup(groupId, areaId) {
  if (!confirm('Deseja retirar esta sub-área desta pasta? (As fotos não serão apagadas)')) return;
  try {
    await API.del(`/api/groups/${groupId}/subareas/${areaId}`);
    route();
  } catch(e) {}
}

async function analyzePosition(aircraftId, position) {
  const btn = document.getElementById('btn-analyze-pos');
  btn.disabled = true;
  btn.innerHTML = '⏳ Analisando…';
  try {
    const res = await API.post(`/api/aircraft/${aircraftId}/analyze`, { position, phase: getPhase() }, 120000);
    const ok  = res.results?.filter(r => r.status === 'OK').length || 0;
    const tot = res.results?.length || 0;
    toast(`✅ ${ok}/${tot} áreas íntegras`, 'ok');
    const damaged = res.results?.find(r => r.analysis_id && r.status !== 'OK');
    if (damaged) go(`/analysis/${damaged.analysis_id}`);
    else renderPositionDetail(document.getElementById('app'), aircraftId, position);
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🔬 Analisar Posição';
  }
}

/* ════════════════════════════════════════════
   VISUALIZADOR DE FOTO
════════════════════════════════════════════ */
async function renderPhotoViewer(app, aircraftId, areaId, mode, position) {
  const label = mode === 'before' ? 'ANTES' : 'DEPOIS';
  const backUrl = position
    ? `/aircraft/${aircraftId}/pos/${position}/area/${areaId}`
    : `/aircraft/${aircraftId}/area/${areaId}`;
  const retakeUrl = position
    ? `/aircraft/${aircraftId}/pos/${position}/area/${areaId}/${mode}`
    : `/aircraft/${aircraftId}/area/${areaId}/${mode}`;

  app.innerHTML = `<div class="app-header">
    <button class="btn-icon" onclick="go('${backUrl}')">‹</button>
    <h1>${label}</h1>
  </div><div class="view" style="padding:0"><div class="spinner" style="padding:40px"></div></div>`;

  const phase = getPhase();
  const phaseEnc = encodeURIComponent(phase);
  const posQ = position ? `?position=${position}&phase=${phaseEnc}` : `?phase=${phaseEnc}`;
  const photos = await API.get(`/api/aircraft/${aircraftId}/areas/${areaId}/photos${posQ}`).catch(() => ({}));
  const photo = mode === 'before' ? photos.before : photos.after;

  if (!photo) { go(backUrl); return; }

  const ts = photo.captured_at ? new Date(photo.captured_at.replace(' ','T')+'Z').toLocaleString('pt-BR') : '';
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('${backUrl}')">‹</button>
      <h1>${label}</h1>
    </div>
    <div style="background:#000;width:100%;min-height:55vh;display:flex;align-items:center;justify-content:center">
      <img src="${photo.url}" style="max-width:100%;max-height:65vh;object-fit:contain">
    </div>
    <div class="view">
      <p style="color:var(--muted);text-align:center;font-size:0.82rem;margin-bottom:16px">${ts}</p>
      <button class="btn btn-primary" onclick="go('${retakeUrl}')"> 📷 Tirar novamente</button>
    </div>`;
}

function downloadReport(aircraftId, position) {
  const phase = getPhase();
  let url = `/api/aircraft/${aircraftId}/report?phase=${encodeURIComponent(phase)}`;
  if (position) url += `&position=${encodeURIComponent(position)}`;
  window.open(url, '_blank');
}

async function renderAreaDetail(app, templateId, aircraftId, position) {
  const isTemplateEdit = !aircraftId;
  const data = await API.get(`/api/areas/${templateId}/mask`);
  const hasMask = data.mask_points && data.mask_points.length > 1;

  if (isTemplateEdit) {
    app.innerHTML = `
      <div class="app-header">
        <button class="btn-icon" onclick="go('/')">‹</button>
        <h1>Modelo: ${esc(data.name)}</h1>
        <button class="btn-icon" style="color:var(--danger)" onclick="deleteArea(${templateId})">🗑</button>
      </div>
      <div class="view">
        <div class="section-label">Visualização do Modelo</div>
        ${hasMask ? `<div class="mask-preview"><img src="${data.mask_thumb}"><span class="mask-badge">Configurado</span></div>` : `<div class="no-mask-banner">Este modelo ainda não tem uma máscara definida.</div>`}
        <button class="btn btn-primary" onclick="${hasMask ? `go('/area/${templateId}/mask')` : `retakeRefPhoto(${templateId})`}">
          ${hasMask ? '✏️ Ajustar Quadrante' : '📷 Tirar Foto Base'}
        </button>
        ${hasMask ? `<button class="btn btn-ghost" onclick="retakeRefPhoto(${templateId})" style="margin-top:10px">📷 Refazer Foto Base</button>` : ''}
      </div>
      <div id="camera-container"></div>`;
    return;
  }

  const phase = getPhase();
  const phaseEnc = encodeURIComponent(phase);
  const posQ = position ? `?position=${position}&phase=${phaseEnc}` : `?phase=${phaseEnc}`;
  const [ac, photos, analyses] = await Promise.all([
    API.get('/api/aircraft').then(list => list.find(a => a.id == aircraftId) || {}),
    API.get(`/api/aircraft/${aircraftId}/areas/${templateId}/photos${posQ}`).catch(() => ({before:null,after:null})),
    API.get(`/api/aircraft/${aircraftId}/areas/${templateId}/analyses${posQ}`).catch(() => []),
  ]);

  const lastAnalysis = analyses[0] || null;
  const backUrl = position ? `/aircraft/${aircraftId}/pos/${position}` : `/aircraft/${aircraftId}`;

  const photoCard = (mode, photo) => {
    const label = mode === 'before' ? 'ANTES' : 'DEPOIS';
    const colorClass = mode === 'before' ? 'before' : 'after';
    const captureUrl = position
      ? `/aircraft/${aircraftId}/pos/${position}/area/${templateId}/${mode}`
      : `/aircraft/${aircraftId}/area/${templateId}/${mode}`;
    const viewUrl = position
      ? `/aircraft/${aircraftId}/pos/${position}/area/${templateId}/${mode}/view`
      : captureUrl;
    if (photo) {
      return `<div class="action-card ${colorClass}" onclick="go('${viewUrl}')">
        <img src="${photo.url}" style="width:100%;height:100%;object-fit:cover;border-radius:12px;opacity:0.85">
        <span class="ac-label" style="position:absolute;bottom:8px;left:0;right:0;text-align:center">${label} ✅</span>
      </div>`;
    }
    return `<div class="action-card ${colorClass}" onclick="go('${captureUrl}')">
      <span class="ac-icon">📸</span>
      <span class="ac-label">${label}</span>
    </div>`;
  };

  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('${backUrl}')">‹</button>
      <h1>${esc(ac.serial)}${position ? ' | '+position : ''}</h1>
    </div>
    <div class="view">
      <div class="section-label">Área: ${esc(data.name)}</div>
      <div class="action-grid" style="position:relative">
        ${photoCard('before', photos.before)}
        ${photoCard('after', photos.after)}
      </div>
      ${photos.before && photos.after ? `
        <button class="btn btn-primary" style="margin-top:16px" onclick="analyzeArea(${aircraftId},${templateId},'${position||''}')" id="btn-analyze">
          🔬 Analisar esta Área
        </button>` : `
        <div class="no-mask-banner" style="margin-top:12px">Bata as fotos ANTES e DEPOIS para analisar.</div>`}
      ${lastAnalysis ? `
        <div class="section-label" style="margin-top:20px">Última Análise</div>
        <div class="card" onclick="go('/analysis/${lastAnalysis.id}')">
          <span class="card-icon">${lastAnalysis.status === 'OK' ? '✅' : '⚠️'}</span>
          <div class="card-body">
            <div class="card-title">${lastAnalysis.status === 'OK' ? 'Íntegro' : 'Diferença detectada'}</div>
            <div class="card-sub">Score: ${lastAnalysis.final_score?.toFixed(3)} · ${lastAnalysis.created_at?.slice(0,16)}</div>
          </div>
          <span style="color:var(--muted);font-size:1.2rem">›</span>
        </div>` : ''}
    </div>`;
}

async function analyzeArea(aircraftId, areaId, position) {
  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.textContent = '⏳ Analisando...';
  try {
    const res = await API.post(`/api/aircraft/${aircraftId}/areas/${areaId}/analyze`, { position: position || null });
    toast('Análise concluída!', 'ok');
    go(`/analysis/${res.analysis_id}`);
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🔬 Analisar esta Área';
  }
}

/* ════════════════════════════════════════════
   NOVO MODELO GLOBAL — Step 1: nome + foto referência
════════════════════════════════════════════ */
function renderNewArea(app) {
  window._refPhotoDataUrl = null;

  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="go('/')">‹</button>
      <h1>Novo modelo global</h1>
    </div>
    <div class="view">
      <div class="form-group">
        <label class="form-label">Nome da área modelo</label>
        <input id="f-areaname" class="form-input" placeholder="ex: Console Central">
      </div>

      <div class="form-group">
        <label class="form-label">Foto de referência (base da máscara)</label>
        <div id="ref-preview" style="margin-bottom:10px"></div>
        <button class="btn btn-ghost" onclick="openRefCamera()">📷 Tirar foto base</button>
      </div>

      <button class="btn btn-primary" id="btn-next" onclick="submitNewArea()" disabled>Próximo → Definir área</button>
    </div>
    <div id="camera-container"></div>`;
}

async function submitNewArea() {
  const name = document.getElementById('f-areaname').value.trim();
  if (!name) { toast('Informe o nome do modelo', 'err'); return; }
  if (!window._refPhotoDataUrl) { toast('Tire a foto de referência primeiro', 'err'); return; }

  try {
    const res = await API.post(`/api/areas`, { name });
    sessionStorage.setItem('refPhoto', window._refPhotoDataUrl);
    go(`/area/${res.id}/mask`);
  } catch(e) {}
}

let _retakeAreaId = null;

function retakeRefPhoto(areaId) {
  _retakeAreaId = areaId;
  openRefCamera();
}

async function openRefCamera() {
  const container = document.getElementById('camera-container');
  container.innerHTML = `
    <div class="camera-screen">
      <video id="ref-video" autoplay playsinline style="width:100%; height:100%; object-fit:cover;"></video>
      <div class="camera-top-bar" style="display:flex; justify-content:flex-end;">
        <button class="btn-icon" onclick="closeRefCamera()" style="color:#fff; background:rgba(0,0,0,0.5)">✕</button>
      </div>
      <div class="camera-bottom-bar">
        <button class="capture-btn" onclick="takeRefPhoto()"></button>
      </div>
    </div>
  `;
  
  const video = document.getElementById('ref-video');
  try {
    await startCamera(video);
  } catch (err) {
    toast('Câmera indisponível', 'err');
    closeRefCamera();
  }
}

function closeRefCamera() {
  stopCamera();
  document.getElementById('camera-container').innerHTML = '';
  _retakeAreaId = null;
}

function takeRefPhoto() {
  const video = document.getElementById('ref-video');
  window._refPhotoDataUrl = captureFrame(video);
  
  if (_retakeAreaId) {
    // Fluxo de refazer foto para área existente
    sessionStorage.setItem('refPhoto', window._refPhotoDataUrl);
    go(`/area/${_retakeAreaId}/mask`);
    closeRefCamera();
    return;
  }
  
  // Fluxo normal de criar nova área (Home)
  const preview = document.getElementById('ref-preview');
  if (preview) {
    preview.innerHTML = `<img src="${window._refPhotoDataUrl}" style="width:100%; max-height:200px; object-fit:contain; border-radius:8px; border:1px solid var(--border);">`;
  }
  
  const btn = document.getElementById('btn-next');
  if (btn) btn.disabled = false;
  
  closeRefCamera();
}

/* ════════════════════════════════════════════
   MASK EDITOR — Seleção de quadrante
════════════════════════════════════════════ */
let _maskRect = null;
let _isDrawing = false;
let _startPos = null;
let _editCanvas = null;
let _editCtx = null;
let _refImg = null;
let _currentAreaId = null;

async function renderMaskEditor(app, areaId) {
  _currentAreaId = areaId;
  _maskRect = null;
  let refSrc = sessionStorage.getItem('refPhoto');

  if (!refSrc) {
    const data = await API.get(`/api/areas/${areaId}/mask`);
    refSrc = data.mask_thumb;
    if (data.mask_points) {
      try {
        const pts = JSON.parse(data.mask_points);
        _maskRect = { x: pts[0][0], y: pts[0][1], w: pts[1][0] - pts[0][0], h: pts[2][1] - pts[1][1] };
      } catch(e){}
    }
  }

  app.innerHTML = `
    <div class="mask-editor-screen">
      <div class="mask-editor-viewport">
        <canvas id="mask-edit-canvas" style="touch-action:none"></canvas>
        <div class="draw-hint">🖱 Arraste para selecionar o quadrante</div>
      </div>
      <div class="mask-editor-toolbar">
        <button class="btn btn-ghost" onclick="clearMask()">🗑 Limpar</button>
        <button class="btn btn-primary" onclick="saveMask()">✓ Confirmar Área</button>
      </div>
    </div>`;

  _editCanvas = document.getElementById('mask-edit-canvas');
  _editCtx = _editCanvas.getContext('2d');

  if (refSrc) {
    _refImg = new Image();
    _refImg.onload = () => { setTimeout(resizeMaskCanvas, 200); };
    _refImg.src = refSrc;
  }

  _editCanvas.addEventListener('pointerdown', maskPointerDown);
  _editCanvas.addEventListener('pointermove', maskPointerMove);
  _editCanvas.addEventListener('pointerup',   maskPointerUp);
}

function resizeMaskCanvas() {
  if (!_editCanvas) return;
  const vp = _editCanvas.parentElement;
  _editCanvas.width = vp.clientWidth;
  _editCanvas.height = vp.clientHeight;
  renderMaskCanvas();
}

function maskPointerDown(e) {
  const r = _editCanvas.getBoundingClientRect();
  _startPos = { x: (e.clientX - r.left) / _editCanvas.width, y: (e.clientY - r.top) / _editCanvas.height };
  _isDrawing = true;
  _maskRect = { x: _startPos.x, y: _startPos.y, w: 0, h: 0 };
}

function maskPointerMove(e) {
  if (!_isDrawing) return;
  const r = _editCanvas.getBoundingClientRect();
  const curX = (e.clientX - r.left) / _editCanvas.width;
  const curY = (e.clientY - r.top) / _editCanvas.height;
  _maskRect = {
    x: Math.min(_startPos.x, curX), y: Math.min(_startPos.y, curY),
    w: Math.abs(curX - _startPos.x), h: Math.abs(curY - _startPos.y)
  };
  renderMaskCanvas();
}

function maskPointerUp() { _isDrawing = false; }

function renderMaskCanvas() {
  if (!_editCtx) return;
  const w = _editCanvas.width, h = _editCanvas.height;
  _editCtx.clearRect(0, 0, w, h);
  if (_refImg) {
    const ir = _refImg.naturalWidth / _refImg.naturalHeight;
    const cr = w / h;
    let sw, sh, sx, sy;
    if (ir > cr) { sh = h; sw = h * ir; sx = (w - sw) / 2; sy = 0; }
    else         { sw = w; sh = w / ir; sx = 0; sy = (h - sh) / 2; }
    _editCtx.drawImage(_refImg, sx, sy, sw, sh);
  }
  if (!_maskRect) return;
  const rx = _maskRect.x * w, ry = _maskRect.y * h, rw = _maskRect.w * w, rh = _maskRect.h * h;
  _editCtx.fillStyle = 'rgba(0,0,0,0.6)';
  _editCtx.fillRect(0,0,w,ry); _editCtx.fillRect(0,ry+rh,w,h-(ry+rh));
  _editCtx.fillRect(0,ry,rx,rh); _editCtx.fillRect(rx+rw,ry,w-(rx+rw),rh);
  _editCtx.strokeStyle = '#58a6ff'; _editCtx.lineWidth = 3; _editCtx.strokeRect(rx, ry, rw, rh);
}

function clearMask() { _maskRect = null; renderMaskCanvas(); }

async function saveMask() {
  if (!_maskRect) { toast('Selecione uma área no quadrante', 'err'); return; }
  const p = _maskRect;
  // Pontos do retângulo para compatibilidade
  const pts = [[p.x, p.y], [p.x+p.w, p.y], [p.x+p.w, p.y+p.h], [p.x, p.y+p.h]];
  
  const tc = document.createElement('canvas');
  tc.width = 300; tc.height = 200;
  tc.getContext('2d').drawImage(_editCanvas, 0, 0, 300, 200);

  try {
    await API.put(`/api/areas/${_currentAreaId}/mask`, {
      points: pts, // Envia como array (o servidor fará o json.dumps)
      thumbnail: tc.toDataURL('image/jpeg', 0.7),
      ref_width: _editCanvas.width, ref_height: _editCanvas.height
    });
    sessionStorage.removeItem('refPhoto');
    toast('Modelo de Máscara salvo ✓', 'ok');
    go('/');
  } catch (err) {}
}

/* ════════════════════════════════════════════
   CAPTURE — Câmera ao vivo + Máscara
════════════════════════════════════════════ */
async function renderCapture(app, aircraftId, areaId, mode, position) {
  toast(`Buscando modelo #${areaId}...`, 'ok');
  
  try {
    const [area, aircraft] = await Promise.all([
      API.get(`/api/areas/${areaId}/mask`),
      API.get('/api/aircraft').then(list => list.find(a => a.id == aircraftId))
    ]);

    if (!area) throw new Error("Dados da máscara vazios");

    // Store context for confirmCrop
    window._captureCtx = { aircraftId, areaId, mode, position };

    app.innerHTML = `
      <div class="camera-screen">
        <div class="camera-viewport">
          <video id="camera-video" autoplay playsinline></video>
          <canvas id="mask-canvas"></canvas>
          <div class="camera-top-bar">
            <button class="btn-icon" onclick="history.back()" style="color:#fff; background:rgba(0,0,0,0.5)">‹</button>
            <div style="flex:1; margin-left:8px;">
              <div style="font-size:1rem;font-weight:bold;color:#fff">${esc(aircraft.serial)}</div>
              <div style="font-size:0.8rem;color:rgba(255,255,255,0.8)">${esc(area.name)}</div>
            </div>
            <span class="camera-mode-badge ${mode}">${mode.toUpperCase()}</span>
          </div>
        </div>
        <div class="camera-bottom-bar">
          <button class="capture-btn" onclick="doCapture('${esc(area.name)}', '${esc(aircraft.serial)}', '${mode}')"></button>
        </div>
      </div>`;

    const video = document.getElementById('camera-video');
    const canvas = document.getElementById('mask-canvas');
    await startCamera(video);

    // Guarda os pontos globalmente para uso no doCapture (recorte)
    const pts = area.mask_points;
    window._currentMaskPts = pts || null;

    if (pts && pts.length > 0) {
      window._rafId = requestAnimationFrame(function draw() {
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = canvas.offsetHeight;
        if (!w || !h) return window._rafId = requestAnimationFrame(draw);
        
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0,0,w,h);
        
        const phase = (Date.now() % 2000) / 2000 * Math.PI * 2;
        const alpha = 0.4 + 0.3 * Math.sin(phase);

        ctx.beginPath();
        ctx.moveTo(pts[0][0]*w, pts[0][1]*h);
        pts.forEach(p => ctx.lineTo(p[0]*w, p[1]*h));
        ctx.closePath();

        ctx.fillStyle = `rgba(88,166,255,${0.1 * alpha})`;
        ctx.fill();

        ctx.shadowColor = '#58a6ff';
        ctx.shadowBlur = 15 * alpha;
        ctx.strokeStyle = `rgba(88,166,255,${alpha + 0.2})`;
        ctx.lineWidth = 4;
        ctx.lineJoin = 'round';
        ctx.stroke();
        ctx.shadowBlur = 0;

        window._rafId = requestAnimationFrame(draw);
      });
    }
  } catch (err) {
    toast(`Erro: ${err.message || 'Falha ao carregar modelo'}`, 'err');
    go('/');
  }
}

function doCapture(areaName, serial, mode) {
  const video = document.getElementById('camera-video');
  const name  = `${serial}_${areaName}_${mode.toUpperCase()}.jpg`;

  // Pausa a câmera e captura o frame completo
  const full = document.createElement('canvas');
  full.width  = video.videoWidth  || video.clientWidth;
  full.height = video.videoHeight || video.clientHeight;
  full.getContext('2d').drawImage(video, 0, 0, full.width, full.height);
  const fullDataUrl = full.toDataURL('image/jpeg', 0.95);

  // Para o stream (câmera) para economizar bateria durante a revisão
  stopCamera();
  cancelAnimationFrame(window._rafId);

  // Abre o editor de recorte pós-captura
  renderCropEditor(fullDataUrl, name);
}

/* ════════════════════════════════════════════
   CROP EDITOR — Seleção de área pós-captura
════════════════════════════════════════════ */
let _cropImg    = null;
let _cropRect   = null;
let _cropStart  = null;
let _cropCanvas = null;
let _cropCtx    = null;
let _cropFileName = '';
let _isCroppingDrag = false;

function renderCropEditor(dataUrl, fileName) {
  _cropFileName = fileName;
  _cropRect     = null;

  // Injeta a tela de revisão sobre o #app
  const overlay = document.createElement('div');
  overlay.id = 'crop-overlay';
  overlay.innerHTML = `
    <canvas id="crop-canvas" style="touch-action:none;"></canvas>
    <div class="camera-top-bar" style="display:flex; align-items:center; gap:10px; z-index:20;">
      <button class="btn-icon" onclick="closeCropEditor()" style="color:#fff; background:rgba(0,0,0,0.5);">‹</button>
      <span style="color:#fff; font-size:0.9rem; flex:1;">Selecione a área a analisar</span>
    </div>
    <div class="camera-bottom-bar" style="position:absolute; bottom:0; left:0; right:0; z-index:20; display:flex; gap:16px; justify-content:center; padding: 16px 24px calc(16px + env(safe-area-inset-bottom, 16px)); background:linear-gradient(to top,rgba(0,0,0,.85),transparent);">
      <button class="btn btn-ghost" onclick="resetCrop()" style="flex:0 1 140px;">🔄 Refazer</button>
      <button class="btn btn-primary" onclick="confirmCrop()" style="flex:0 1 180px;">✓ Confirmar Área</button>
    </div>`;
  document.body.appendChild(overlay);

  _cropCanvas = document.getElementById('crop-canvas');
  _cropCtx    = _cropCanvas.getContext('2d');

  _cropImg = new Image();
  _cropImg.onload = () => {
    // Tamanho responsivo
    _cropCanvas.width  = window.innerWidth;
    _cropCanvas.height = window.innerHeight;

    // Pré-carrega o rect com as coordenadas da máscara salva
    const pts = window._currentMaskPts;
    if (pts && pts.length >= 2) {
      const xs = pts.map(p => p[0]);
      const ys = pts.map(p => p[1]);
      _cropRect = {
        x: Math.min(...xs),
        y: Math.min(...ys),
        w: Math.max(...xs) - Math.min(...xs),
        h: Math.max(...ys) - Math.min(...ys),
      };
    }
    drawCropEditor();
  };
  _cropImg.src = dataUrl;

  _cropCanvas.addEventListener('pointerdown', cropPointerDown);
  _cropCanvas.addEventListener('pointermove', cropPointerMove);
  _cropCanvas.addEventListener('pointerup',   cropPointerUp);
}

function drawCropEditor() {
  if (!_cropCtx || !_cropImg) return;
  const W = _cropCanvas.width;
  const H = _cropCanvas.height;

  // Desenha foto de fundo (fit)
  _cropCtx.clearRect(0, 0, W, H);
  const ir = _cropImg.naturalWidth / _cropImg.naturalHeight;
  const cr = W / H;
  let sw, sh, sx, sy;
  if (ir > cr) { sh = H; sw = H * ir; sx = (W - sw) / 2; sy = 0; }
  else         { sw = W; sh = W / ir; sx = 0; sy = (H - sh) / 2; }
  _cropCtx.drawImage(_cropImg, sx, sy, sw, sh);

  if (!_cropRect) return;

  const rx = _cropRect.x * W;
  const ry = _cropRect.y * H;
  const rw = _cropRect.w * W;
  const rh = _cropRect.h * H;

  // Escurece fora da seleção
  _cropCtx.fillStyle = 'rgba(0,0,0,0.55)';
  _cropCtx.fillRect(0, 0, W, ry);
  _cropCtx.fillRect(0, ry + rh, W, H - (ry + rh));
  _cropCtx.fillRect(0, ry, rx, rh);
  _cropCtx.fillRect(rx + rw, ry, W - (rx + rw), rh);

  // Borda da seleção com glow
  _cropCtx.shadowColor = '#58a6ff';
  _cropCtx.shadowBlur  = 12;
  _cropCtx.strokeStyle = '#58a6ff';
  _cropCtx.lineWidth   = 3;
  _cropCtx.strokeRect(rx, ry, rw, rh);
  _cropCtx.shadowBlur  = 0;

  // Alças nos cantos
  const grip = 14;
  _cropCtx.strokeStyle = '#fff';
  _cropCtx.lineWidth   = 3;
  [[rx, ry],[rx+rw, ry],[rx, ry+rh],[rx+rw, ry+rh]].forEach(([cx, cy]) => {
    _cropCtx.strokeRect(cx - grip/2, cy - grip/2, grip, grip);
  });
}

function cropPointerDown(e) {
  const r = _cropCanvas.getBoundingClientRect();
  _cropStart = { x: (e.clientX - r.left) / _cropCanvas.width, y: (e.clientY - r.top) / _cropCanvas.height };
  _isCroppingDrag = true;
  _cropRect = { x: _cropStart.x, y: _cropStart.y, w: 0, h: 0 };
}

function cropPointerMove(e) {
  if (!_isCroppingDrag) return;
  const r   = _cropCanvas.getBoundingClientRect();
  const curX = (e.clientX - r.left) / _cropCanvas.width;
  const curY = (e.clientY - r.top)  / _cropCanvas.height;
  _cropRect = {
    x: Math.min(_cropStart.x, curX), y: Math.min(_cropStart.y, curY),
    w: Math.abs(curX - _cropStart.x), h: Math.abs(curY - _cropStart.y),
  };
  drawCropEditor();
}

function cropPointerUp() { _isCroppingDrag = false; }

function resetCrop() {
  _cropRect = null;
  drawCropEditor();
}

function closeCropEditor() {
  document.getElementById('crop-overlay')?.remove();
  history.back();
}

async function confirmCrop() {
  if (!_cropRect || _cropRect.w < 0.02 || _cropRect.h < 0.02) {
    toast('Selecione uma área maior', 'err');
    return;
  }

  const W = _cropCanvas.width;
  const H = _cropCanvas.height;
  const cropX = Math.round(_cropRect.x * W);
  const cropY = Math.round(_cropRect.y * H);
  const cropW = Math.round(_cropRect.w * W);
  const cropH = Math.round(_cropRect.h * H);

  const out = document.createElement('canvas');
  out.width  = cropW;
  out.height = cropH;
  out.getContext('2d').drawImage(_cropCanvas, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);
  const dataUrl = out.toDataURL('image/jpeg', 0.92);

  // Get context from window._captureCtx (new) or hash (legacy)
  let aircraftId, areaId, mode, position = null;
  const ctx = window._captureCtx;
  if (ctx) {
    ({ aircraftId, areaId, mode, position } = ctx);
    window._captureCtx = null;
  } else {
    const h = location.hash.slice(1);
    // Try new route: /aircraft/:id/pos/:pos/area/:aid/:mode
    let m = h.match(/\/aircraft\/(\d+)\/pos\/([A-Z0-9]+)\/area\/(\d+)\/(before|after)/);
    if (m) { [, aircraftId, position, areaId, mode] = m; }
    else {
      // Legacy: /aircraft/:id/area/:aid/:mode
      m = h.match(/\/aircraft\/(\d+)\/area\/(\d+)\/(before|after)/);
      if (m) { [, aircraftId, areaId, mode] = m; }
    }
  }

  if (aircraftId && areaId && mode) {
    const btn = document.querySelector('#crop-overlay .btn-primary');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Enviando...'; }
    try {
      await API.post('/api/photos/upload', {
        aircraft_id: parseInt(aircraftId),
        area_id:     parseInt(areaId),
        mode,
        position:    position || null,
        phase:       getPhase(),
        image:       dataUrl,
      });
      toast('✅ Foto enviada!', 'ok');
    } catch(e) {
      toast('Falha ao enviar foto', 'err');
      if (btn) { btn.disabled = false; btn.textContent = '✓ Confirmar Área'; }
      return;
    }
  }

  document.getElementById('crop-overlay')?.remove();
  history.back();
}

async function deleteAircraft(id) {
  if (!confirm('Tem certeza que deseja remover esta aeronave?')) return;
  try {
    await API.del(`/api/aircraft/${id}`);
    toast('Aeronave removida', 'ok');
    go('/');
  } catch (e) {}
}

async function deleteArea(id) {
  if (!confirm('Tem certeza que deseja remover este modelo de máscara?')) return;
  try {
    await API.del(`/api/areas/${id}`);
    toast('Modelo removido', 'ok');
    go('/');
  } catch (e) {}
}

/* ── Utilities ── */
function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ════════════════════════════════════════════
   RESULTADO DA ANÁLISE
════════════════════════════════════════════ */
async function renderAnalysisResult(app, analysisId) {
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="history.back()">‹</button>
      <h1>Resultado da Análise</h1>
    </div>
    <div class="view"><div class="spinner"></div></div>`;

  const r = await API.get(`/api/analyses/${analysisId}`).catch(() => null);
  if (!r) { app.querySelector('.view').innerHTML = '<p>Análise não encontrada.</p>'; return; }

  const statusColor = r.status === 'OK' ? 'var(--success, #3fb950)' : 'var(--warning, #d29922)';
  const statusLabel = r.status === 'OK' ? '✅ Estrutura Íntegra' : '⚠️ Diferença Detectada';

  app.querySelector('.view').innerHTML = `
    <div style="text-align:center; padding:16px 0;">
      <div style="font-size:2.5rem; margin-bottom:8px">${r.status === 'OK' ? '✅' : '⚠️'}</div>
      <div style="font-size:1.3rem; font-weight:bold; color:${statusColor}">${statusLabel}</div>
      <div style="color:var(--muted); font-size:0.85rem; margin-top:4px">${r.created_at?.slice(0,16) || ''}</div>
    </div>

    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin:16px 0;">
      <div class="score-box">
        <div class="score-value">${r.emb_score?.toFixed(3)}</div>
        <div class="score-label">Semântico</div>
      </div>
      <div class="score-box">
        <div class="score-value">${r.orb_score?.toFixed(3)}</div>
        <div class="score-label">ORB</div>
      </div>
      <div class="score-box" style="border-color:${statusColor}">
        <div class="score-value" style="color:${statusColor}">${r.final_score?.toFixed(3)}</div>
        <div class="score-label">Final</div>
      </div>
    </div>

    ${r.heatmap_url ? `
      <div class="section-label">Mapa de Calor</div>
      <img src="${r.heatmap_url}" style="width:100%; border-radius:12px; margin-bottom:16px; object-fit:contain;">
    ` : ''}

    <button class="btn btn-primary" onclick="go('/feedback/${analysisId}')">
      📝 Avaliar esta análise
    </button>`;
}

/* ════════════════════════════════════════════
   FEEDBACK — Avaliação humana para treino
════════════════════════════════════════════ */
async function renderFeedback(app, analysisId) {
  app.innerHTML = `
    <div class="app-header">
      <button class="btn-icon" onclick="history.back()">‹</button>
      <h1>Avaliar Análise</h1>
    </div>
    <div class="view">
      <p style="color:var(--muted);font-size:0.9rem;margin-bottom:20px">
        Sua avaliação ajuda a treinar o modelo de IA para inspeções futuras.
      </p>

      <div class="section-label">A classificação está correta?</div>
      <div style="display:flex; gap:10px; margin-bottom:20px;">
        <button class="btn btn-ghost" id="cls-yes" onclick="setFeedback('cls', true)">✅ Sim</button>
        <button class="btn btn-ghost" id="cls-no"  onclick="setFeedback('cls', false)">❌ Não</button>
      </div>

      <div class="section-label">O local do dano está correto?</div>
      <div style="display:flex; gap:10px; margin-bottom:12px;">
        <button class="btn btn-ghost" id="loc-yes" onclick="setFeedback('loc', true)">✅ Sim</button>
        <button class="btn btn-ghost" id="loc-no"  onclick="setFeedback('loc', false)">❌ Não (marcar correto)</button>
      </div>

      <div id="region-editor" style="display:none; margin-bottom:16px;">
        <div style="color:var(--muted);font-size:0.85rem;margin-bottom:8px">
          Arraste para marcar o local correto do dano:
        </div>
        <canvas id="fb-canvas" style="width:100%;border-radius:10px;touch-action:none;cursor:crosshair;"></canvas>
      </div>

      <div class="form-group" style="margin-top:8px;">
        <label class="form-label">Observações (opcional)</label>
        <textarea id="fb-notes" class="form-input" rows="3" placeholder="Ex: Amassado na longarina direita..."></textarea>
      </div>

      <button class="btn btn-primary" onclick="submitFeedback(${analysisId})">Enviar Avaliação</button>
    </div>`;

  // Carrega heatmap como background do canvas de feedback
  const r = await API.get(`/api/analyses/${analysisId}`).catch(() => null);
  if (r?.heatmap_url) {
    const canvas = document.getElementById('fb-canvas');
    const img    = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      canvas.width  = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.style.maxHeight = '200px';
      canvas.getContext('2d').drawImage(img, 0, 0);
      attachFbDraw(canvas);
    };
    img.src = r.heatmap_url;
  }
}

const _fb = { cls: null, loc: null, region: null };

function setFeedback(key, val) {
  _fb[key] = val;
  const yes = document.getElementById(`${key}-yes`);
  const no  = document.getElementById(`${key}-no`);
  yes.classList.toggle('btn-primary', val === true);
  yes.classList.toggle('btn-ghost',   val !== true);
  no.classList.toggle('btn-primary',  val === false);
  no.classList.toggle('btn-ghost',    val !== false);
  if (key === 'loc' && val === false) {
    document.getElementById('region-editor').style.display = 'block';
  }
}

function attachFbDraw(canvas) {
  let drawing = false, sx, sy;
  const ctx = canvas.getContext('2d');
  canvas.addEventListener('pointerdown', e => {
    drawing = true;
    const r = canvas.getBoundingClientRect();
    const scale = canvas.width / r.width;
    sx = (e.clientX - r.left) * scale;
    sy = (e.clientY - r.top)  * scale;
  });
  canvas.addEventListener('pointermove', e => {
    if (!drawing) return;
    const r = canvas.getBoundingClientRect();
    const scale = canvas.width / r.width;
    const cx = (e.clientX - r.left) * scale;
    const cy = (e.clientY - r.top)  * scale;
    ctx.strokeStyle = '#f85149';
    ctx.lineWidth = 4;
    ctx.strokeRect(sx, sy, cx - sx, cy - sy);
    _fb.region = { x: Math.min(sx,cx)/canvas.width, y: Math.min(sy,cy)/canvas.height,
                   w: Math.abs(cx-sx)/canvas.width,  h: Math.abs(cy-sy)/canvas.height };
  });
  canvas.addEventListener('pointerup', () => { drawing = false; });
}

async function submitFeedback(analysisId) {
  if (_fb.cls === null) { toast('Responda se a classificação está correta', 'err'); return; }
  if (_fb.loc === null) { toast('Responda se o local está correto', 'err'); return; }
  const notes = document.getElementById('fb-notes')?.value.trim() || '';
  try {
    await API.post('/api/feedback', {
      analysis_id:             parseInt(analysisId),
      classification_correct:  _fb.cls,
      damage_location_correct: _fb.loc,
      corrected_region:        _fb.region || null,
      notes,
    });
    toast('✅ Avaliação enviada! Obrigado.', 'ok');
    history.back();
  } catch(e) {}
}

