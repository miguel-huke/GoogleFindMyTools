const map = L.map('map', { zoomControl: false }).setView([-23.5505, -46.6333], 10);
L.control.zoom({ position: 'topright' }).addTo(map);

const tileLayer = L.tileLayer('/osm-tiles/{z}/{x}/{y}.png', {
  minZoom: 0,
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
});
tileLayer.addTo(map);

const markerLayer = L.layerGroup().addTo(map);
const trackLayer = L.layerGroup().addTo(map);
const state = { devices: [], reports: [] };
const colors = ['#55f2ad', '#4bd9ed', '#f3c96b', '#f28ac5', '#a994ff'];
const $ = (selector) => document.querySelector(selector);
const status = $('#status');
const loadButton = $('#load-devices');
const locateAllButton = $('#locate-all');

tileLayer.on('tileerror', () => {
  setStatus('Falha ao carregar os tiles do mapa-base pelo servidor local.', true);
});

loadButton.addEventListener('click', loadDevices);
locateAllButton.addEventListener('click', locateAll);

async function api(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function loadDevices() {
  setBusy(true, 'Conectando. A janela oficial de login poderá ser aberta pelo backend...');
  try {
    const payload = await api('/api/devices');
    state.devices = payload.devices;
    state.reports = [];
    renderDevices(); renderReports(); renderMap();
    locateAllButton.disabled = state.devices.length === 0;
    setStatus(`${state.devices.length} device(s) disponível(is). Escolha Localizar ou atualize todos.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    loadButton.disabled = false;
  }
}

async function locateAll() {
  locateAllButton.disabled = true;
  state.reports = [];
  for (const device of state.devices) await locateDevice(device, false);
  locateAllButton.disabled = false;
  setStatus(`${state.reports.length} report(s) alinhado(s) no mapa.`);
}

async function locateDevice(device, announce = true) {
  setStatus(`Solicitando reports de ${device.name}...`);
  try {
    const payload = await api(`/api/devices/${encodeURIComponent(device.ref)}/reports`);
    state.reports = state.reports.filter((item) => item.device.ref !== device.ref);
    const located = payload.reports
      .filter((report) => report.kind === 'point')
      .map((report) => ({ ...report, device: payload.device }));
    state.reports.push(...located);
    renderReports(); renderMap();
    if (announce) setStatus(`${located.length} report(s) de ${device.name} no mapa.`);
  } catch (error) {
    setStatus(`${device.name}: ${error.message}`, true);
  }
}

function renderDevices() {
  $('#device-count').textContent = state.devices.length;
  const list = $('#device-list');
  list.replaceChildren(...state.devices.map((device) => {
    const item = document.createElement('article'); item.className = 'device';
    const label = document.createElement('div');
    const strong = document.createElement('strong'); strong.textContent = device.name;
    const small = document.createElement('small'); small.textContent = 'Referência temporária protegida';
    label.append(strong, small);
    const button = document.createElement('button'); button.textContent = 'Localizar';
    button.addEventListener('click', () => locateDevice(device));
    item.append(label, button); return item;
  }));
}

function renderReports() {
  const ordered = [...state.reports].sort((a, b) => b.timestamp - a.timestamp);
  $('#report-count').textContent = ordered.length;
  const list = $('#report-list');
  list.replaceChildren(...ordered.map((report) => {
    const item = document.createElement('article'); item.className = 'report';
    const strong = document.createElement('strong'); strong.textContent = report.device.name;
    const small = document.createElement('small');
    small.textContent = `${formatTime(report.timestamp)} · ±${Math.round(report.accuracy)} m · ${report.status}`;
    item.append(strong, small);
    item.addEventListener('click', () => map.flyTo([report.latitude, report.longitude], 15));
    return item;
  }));
}

function renderMap() {
  markerLayer.clearLayers(); trackLayer.clearLayers();
  const bounds = [];
  state.devices.forEach((device, index) => {
    const color = colors[index % colors.length];
    const reports = state.reports
      .filter((item) => item.device.ref === device.ref)
      .sort((a, b) => a.timestamp - b.timestamp);
    const points = reports.map((report) => [report.latitude, report.longitude]);
    if (points.length > 1) L.polyline(points, { color, weight: 3, opacity: .82 }).addTo(trackLayer);
    reports.forEach((report) => {
      const point = [report.latitude, report.longitude];
      if (report.accuracy > 0) {
        L.circle(point, { radius: report.accuracy, color, weight: 1, opacity: .45, fillOpacity: .08 }).addTo(markerLayer);
      }
      L.circleMarker(point, {
        radius: 8, color: '#07100f', weight: 3,
        fillColor: report.is_own_report ? '#55f2ad' : '#4bd9ed', fillOpacity: 1,
      }).bindPopup(
        `<strong>${escapeHtml(device.name)}</strong><br>${escapeHtml(formatTime(report.timestamp))}<br>` +
        `Precisão: ±${Math.round(report.accuracy)} m<br>Altitude: ${report.altitude} m`
      ).addTo(markerLayer);
      bounds.push(point);
    });
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [70, 70], maxZoom: 16 });
  window.setTimeout(() => map.invalidateSize(), 0);
}

function setBusy(disabled, message) { loadButton.disabled = disabled; locateAllButton.disabled = disabled; setStatus(message); }
function setStatus(message, isError = false) { status.textContent = message; status.classList.toggle('error', isError); }
function formatTime(timestamp) { return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(timestamp * 1000)); }
function escapeHtml(value) { const node = document.createElement('span'); node.textContent = value; return node.innerHTML; }
