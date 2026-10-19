const API_BASE = '/api/v1';
const TERMINAL_STATES = new Set(['SUCCEEDED', 'PARTIAL', 'FAILED', 'TIMED_OUT', 'CANCELLED']);
const colors = ['#55f2ad', '#4bd9ed', '#f3c96b', '#f28ac5', '#a994ff'];
const $ = (selector) => document.querySelector(selector);
const state = { devices: [], latest: [], histories: new Map(), busy: false, csrfToken: null };

const map = L.map('map', { zoomControl: false }).setView([-23.5505, -46.6333], 10);
L.control.zoom({ position: 'topright' }).addTo(map);
const tileLayer = L.tileLayer('/osm-tiles/{z}/{x}/{y}.png', {
  minZoom: 0,
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
}).addTo(map);
const markerLayer = L.layerGroup().addTo(map);
const trackLayer = L.layerGroup().addTo(map);

const syncButton = $('#sync-devices');
const refreshAllButton = $('#refresh-all');
const statusNode = $('#status');
const progressNode = $('#job-progress');
const progressBar = $('#progress-bar');
const progressLabel = $('#progress-label');

syncButton.addEventListener('click', () => submitAndTrack('/sync/devices', 'Sincronizando devices'));
refreshAllButton.addEventListener('click', () => submitAndTrack('/sync/locations', 'Atualizando localizações'));
tileLayer.on('tileerror', () => setStatus('O mapa-base local não respondeu. Os pontos continuam disponíveis.', true));

async function api(path, options = {}) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  if (options.method === 'POST' && state.csrfToken) headers['X-FindHub-CSRF'] = state.csrfToken;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  let payload;
  try {
    payload = await response.json();
  } catch (_) {
    throw new Error(`Resposta inválida do servidor (HTTP ${response.status}).`);
  }
  if (!response.ok) {
    throw new Error(payload.error?.message || `Falha HTTP ${response.status}.`);
  }
  return payload;
}

async function loadSession() {
  const session = await api('/session');
  if (!session.csrf_token) throw new Error('Sessão local sem proteção CSRF.');
  state.csrfToken = session.csrf_token;
}

async function loadCache() {
  const [devicesPayload, mapPayload] = await Promise.all([api('/devices'), api('/map/latest')]);
  state.devices = devicesPayload.devices;
  state.latest = mapPayload.features.map(pointFromFeature);
  state.histories.clear();
  renderAll();
}

function pointFromFeature(feature) {
  const [longitude, latitude] = feature.geometry.coordinates;
  return {
    device_public_id: feature.properties.device_public_id,
    device_name: feature.properties.name,
    kind: 'point', latitude, longitude,
    observed_at: feature.properties.observed_at,
    accuracy: feature.properties.accuracy,
    status: feature.properties.status,
    own_report: feature.properties.own_report,
    altitude: null,
  };
}

async function submitAndTrack(path, label) {
  setBusy(true);
  showProgress(0, `${label}…`);
  try {
    const submitted = await api(path, { method: 'POST' });
    const result = await pollJob(submitted.job_id, label);
    await loadCache();
    const suffix = result.safe_error ? ` ${result.safe_error}` : '';
    setStatus(`${label}: ${result.status}.${suffix}`, result.status === 'FAILED');
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
    window.setTimeout(() => { progressNode.hidden = true; }, 700);
  }
}

async function pollJob(jobId, label) {
  for (;;) {
    const job = await api(`/jobs/${encodeURIComponent(jobId)}`);
    showProgress(job.progress, `${label}: ${job.completed}/${job.total} · ${job.status}`);
    if (TERMINAL_STATES.has(job.status)) return job;
    await new Promise((resolve) => window.setTimeout(resolve, 200));
  }
}

async function refreshDevice(device) {
  await submitAndTrack(`/devices/${encodeURIComponent(device.public_id)}/refresh`, `Atualizando ${device.name}`);
}

async function loadHistory(device) {
  setBusy(true);
  setStatus(`Carregando histórico local de ${device.name}…`);
  try {
    const payload = await api(`/devices/${encodeURIComponent(device.public_id)}/locations?limit=100`);
    const points = payload.locations
      .filter((location) => location.kind === 'point')
      .map((location) => ({ ...location, device_public_id: device.public_id, device_name: device.name }));
    state.histories.set(device.public_id, points);
    renderAll();
    setStatus(`${points.length} posição(ões) de ${device.name} carregada(s) do SQLite.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
}

function visibleReports() {
  const expanded = new Set(state.histories.keys());
  const reports = state.latest.filter((report) => !expanded.has(report.device_public_id));
  for (const history of state.histories.values()) reports.push(...history);
  return reports;
}

function renderAll() {
  renderDevices();
  renderReports();
  renderMap();
  syncButton.disabled = state.busy;
  refreshAllButton.disabled = state.busy || state.devices.length === 0;
}

function renderDevices() {
  $('#device-count').textContent = state.devices.length;
  const items = state.devices.map((device) => {
    const item = document.createElement('article');
    item.className = 'device';
    const label = document.createElement('div');
    const strong = document.createElement('strong');
    strong.textContent = device.name;
    const small = document.createElement('small');
    small.textContent = device.active ? 'Ativo · cache local' : 'Inativo · cache local';
    label.append(strong, small);
    const actions = document.createElement('div');
    actions.className = 'device-actions';
    const refresh = document.createElement('button');
    refresh.textContent = 'Atualizar';
    refresh.disabled = state.busy;
    refresh.addEventListener('click', () => refreshDevice(device));
    const history = document.createElement('button');
    history.textContent = 'Histórico';
    history.disabled = state.busy;
    history.addEventListener('click', () => loadHistory(device));
    actions.append(refresh, history);
    item.append(label, actions);
    return item;
  });
  $('#device-list').replaceChildren(...items);
}

function renderReports() {
  const ordered = [...visibleReports()].sort((a, b) => b.observed_at - a.observed_at);
  $('#report-count').textContent = ordered.length;
  const items = ordered.map((report) => {
    const item = document.createElement('article');
    item.className = 'report';
    const strong = document.createElement('strong');
    strong.textContent = report.device_name;
    const small = document.createElement('small');
    const accuracy = report.accuracy == null ? 'precisão desconhecida' : `±${Math.round(report.accuracy)} m`;
    small.textContent = `${formatTime(report.observed_at)} · ${formatAge(report.observed_at)} · ${accuracy} · ${report.status}`;
    item.append(strong, small);
    item.addEventListener('click', () => map.flyTo([report.latitude, report.longitude], 15));
    return item;
  });
  $('#report-list').replaceChildren(...items);
}

function renderMap() {
  markerLayer.clearLayers();
  trackLayer.clearLayers();
  const bounds = [];
  const reports = visibleReports();
  state.devices.forEach((device, index) => {
    const color = colors[index % colors.length];
    const deviceReports = reports
      .filter((report) => report.device_public_id === device.public_id)
      .sort((a, b) => a.observed_at - b.observed_at);
    const points = deviceReports.map((report) => [report.latitude, report.longitude]);
    if (state.histories.has(device.public_id) && points.length > 1) {
      L.polyline(points, { color, weight: 3, opacity: 0.82 }).addTo(trackLayer);
    }
    deviceReports.forEach((report) => {
      const point = [report.latitude, report.longitude];
      if (report.accuracy > 0) {
        L.circle(point, { radius: report.accuracy, color, weight: 1, opacity: 0.45, fillOpacity: 0.08 }).addTo(markerLayer);
      }
      const popup = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = device.name;
      const details = document.createElement('span');
      details.textContent = `${formatTime(report.observed_at)} · precisão ${report.accuracy ?? 'desconhecida'} m`;
      popup.append(title, document.createElement('br'), details);
      L.circleMarker(point, {
        radius: 8, color: '#07100f', weight: 3,
        fillColor: report.own_report ? '#55f2ad' : '#4bd9ed', fillOpacity: 1,
      }).bindPopup(popup).addTo(markerLayer);
      bounds.push(point);
    });
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [70, 70], maxZoom: 16 });
  window.setTimeout(() => map.invalidateSize(), 0);
}

function setBusy(value) {
  state.busy = value;
  renderDevices();
  syncButton.disabled = value;
  refreshAllButton.disabled = value || state.devices.length === 0;
}

function showProgress(progress, label) {
  const normalized = Math.max(0, Math.min(1, Number(progress) || 0));
  progressNode.hidden = false;
  progressBar.style.width = `${Math.round(normalized * 100)}%`;
  progressLabel.textContent = label;
}

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle('error', isError);
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })
    .format(new Date(timestamp * 1000));
}

function formatAge(timestamp) {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000) - timestamp);
  if (seconds < 60) return 'há menos de 1 min';
  if (seconds < 3600) return `há ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `há ${Math.floor(seconds / 3600)} h`;
  return `há ${Math.floor(seconds / 86400)} d`;
}

async function bootstrap() {
  try {
    await loadSession();
    await loadCache();
    setStatus(`${state.devices.length} device(s) e ${state.latest.length} posição(ões) carregados do SQLite.`);
    window.__findHubReady = true;
    window.__findHubState = state;
  } catch (error) {
    setStatus(error.message, true);
    window.__findHubReady = false;
  }
}

bootstrap();
