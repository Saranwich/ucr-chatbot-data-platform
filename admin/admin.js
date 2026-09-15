'use strict';

const $ = (id) => document.getElementById(id);
const API = '/api/admin';
const PAGE_SIZE = 100;
const types = { flood: 'Flood', heat: 'Heat', light: 'Street lighting', other: 'Other' };
const colors = { flood: '#236db0', heat: '#bd4e26', light: '#987300', other: '#635397' };
let map, markers, reportOffset = 0, reportTotal = 0, loadedReports = [];
let reportVersion = 0, detailVersion = 0, usersOffset = 0, usersLoaded = false;
let broadcastOffset = 0, selectedBroadcast = null, pollTimer;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options, headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((e) => e.msg).join('; ');
      else if (data.detail?.message) message = data.detail.message;
    } catch { /* Preserve the HTTP error if the response is not JSON. */ }
    throw new Error(message);
  }
  return response.json();
}
async function guarded(button, action) {
  if (button) button.disabled = true;
  try { await action(); } catch (error) { notice(error.message, true); }
  finally { if (button) button.disabled = false; }
}
function date(value) { return value ? new Date(value).toLocaleString() : '—'; }
function field(list, label, value) {
  list.append(node('dt', label), node('dd', value == null ? 'Unknown' : String(value)));
}
function createMap() {
  if (map) return;
  if (!window.L) {
    $('map').replaceChildren(node('p', 'The map library could not load. Reports remain available below.'));
    return;
  }
  map = L.map('map').setView([13.75, 100.5], 6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  markers = L.featureGroup().addTo(map);
}
function renderReports() {
  $('report-list').replaceChildren();
  if (markers) markers.clearLayers();
  let pinCount = 0;
  for (const report of loadedReports) {
    const button = node('button', undefined, 'report-card');
    button.type = 'button';
    button.append(node('strong', report.title || 'Untitled report'));
    const pins = (report.locations || []).filter((loc) => loc.lat != null && loc.lon != null);
    button.append(node('span', `${types[report.type] || 'Unclassified'} · ${pins.length ? `${pins.length} location(s)` : 'No coordinates'}`));
    button.addEventListener('click', () => guarded(button, () => showReport(report.id)));
    $('report-list').append(button);
    for (const location of pins) {
      pinCount += 1;
      if (!markers) continue;
      const pin = L.circleMarker([location.lat, location.lon], {
        radius: 8, color: colors[report.type] || '#586773', weight: 2, fillOpacity: .75,
      }).addTo(markers);
      const popup = node('div');
      popup.append(node('strong', report.title || 'Untitled report'));
      const open = node('button', 'View details');
      open.type = 'button';
      open.addEventListener('click', () => guarded(open, () => showReport(report.id)));
      popup.append(node('br'), open);
      pin.bindPopup(popup);
      pin.on('click', () => guarded(null, () => showReport(report.id)));
    }
  }
  if (!loadedReports.length) $('report-list').append(node('p', 'No reports found.'));
  $('report-summary').textContent = `${loadedReports.length} of ${reportTotal} reports loaded · ${pinCount} map spots. Load more to include older reports on the map.`;
  $('load-more').hidden = reportOffset >= reportTotal;
  if (markers && markers.getLayers().length) map.fitBounds(markers.getBounds(), { padding: [25, 25], maxZoom: 16 });
}
async function loadReports(reset = true) {
  const version = ++reportVersion;
  const offset = reset ? 0 : reportOffset;
  const filter = $('type-filter').value;
  const data = await api(`/reports?limit=${PAGE_SIZE}&offset=${offset}${filter ? `&type=${encodeURIComponent(filter)}` : ''}`);
  if (version !== reportVersion) return;
  loadedReports = reset ? data.items : [...loadedReports, ...data.items];
  reportOffset = offset + data.items.length;
  reportTotal = data.total;
  renderReports();
}
async function showReport(id) {
  const version = ++detailVersion;
  $('report-detail').replaceChildren(node('p', 'Loading report…'));
  let report;
  try { report = await api(`/reports/${encodeURIComponent(id)}`); }
  catch (error) {
    if (version === detailVersion) $('report-detail').replaceChildren(node('p', error.message));
    throw error;
  }
  if (version !== detailVersion) return;
  const panel = $('report-detail');
  panel.replaceChildren(node('h2', report.title || 'Untitled report'));
  const details = node('dl');
  field(details, 'Type', types[report.type] || report.type);
  field(details, 'Threat', report.threat);
  field(details, 'Frequency', report.frequency);
  field(details, 'Effect', report.effect);
  field(details, 'Status', report.status);
  field(details, 'Created', date(report.created_at));
  panel.append(details, node('h3', 'Locations'));
  if (!report.locations?.length) panel.append(node('p', 'No coordinates linked to this report.'));
  for (const location of report.locations || []) {
    panel.append(node('p', location.address || 'Shared location'));
    if (location.lat != null && location.lon != null) {
      const zoom = node('button', `${location.lat}, ${location.lon} · Show on map`);
      zoom.type = 'button';
      zoom.disabled = !map;
      zoom.addEventListener('click', () => map.setView([location.lat, location.lon], 17));
      panel.append(zoom);
    }
  }
  panel.append(node('h3', 'Images'));
  const photos = node('div', undefined, 'photos');
  for (const image of report.images || []) {
    const link = node('a');
    link.href = image.url;
    link.target = '_blank';
    link.rel = 'noopener';
    const img = node('img');
    img.src = image.url;
    img.alt = image.desc || 'Image attached to this report';
    img.loading = 'lazy';
    img.addEventListener('error', () => link.replaceChildren(node('span', 'Image file unavailable.')));
    link.append(img);
    photos.append(link);
    if (image.desc) photos.append(node('p', image.desc));
  }
  panel.append(photos);
  if (!report.images?.length) panel.append(node('p', 'No images linked to this report.'));
}
function countTable(title, counts) {
  const group = node('div', undefined, 'stat-group');
  group.append(node('h2', title));
  const table = node('table');
  const head = node('tr');
  head.append(node('th', title === 'Reports by type' ? 'Type' : 'Status'), node('th', 'Count'));
  const thead = node('thead'); thead.append(head); table.append(thead);
  const body = node('tbody');
  for (const [key, count] of Object.entries(counts)) {
    const row = node('tr'); row.append(node('td', types[key] || key), node('td', count)); body.append(row);
  }
  table.append(body); group.append(table);
  if (!Object.keys(counts).length) group.append(node('p', 'No data yet.'));
  return group;
}
function dailyChart(days) {
  const group = node('div', undefined, 'stat-group daily-chart');
  group.append(node('h2', 'Report records over time'), node('p', 'Daily totals · Bangkok time', 'muted'));
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 1000 240');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Daily report counts. Highest daily count: ${Math.max(0, ...days.map((day) => day.count))}. Exact values are in the table below.`);
  const max = Math.max(1, ...days.map((day) => day.count));
  const step = 940 / Math.max(1, days.length);
  for (let i = 0; i < days.length; i += 1) {
    const bar = document.createElementNS(svgNS, 'rect');
    const height = days[i].count / max * 190;
    for (const [key, value] of Object.entries({ x: 45 + i * step, y: 205 - height, width: Math.max(1, step * .78), height, fill: '#1768a6' })) bar.setAttribute(key, value);
    const title = document.createElementNS(svgNS, 'title'); title.textContent = `${days[i].date}: ${days[i].count} reports`; bar.append(title); svg.append(bar);
  }
  for (const [x, y, text] of [[0, 20, String(max)], [0, 205, '0'], [45, 235, days[0]?.date || ''], [835, 235, days.at(-1)?.date || '']]) {
    const label = document.createElementNS(svgNS, 'text'); label.setAttribute('x', x); label.setAttribute('y', y); label.setAttribute('font-size', '16'); label.textContent = text; svg.append(label);
  }
  group.append(svg);
  const disclosure = node('details'); disclosure.append(node('summary', 'Show daily counts'));
  const table = node('table'); const head = node('tr'); head.append(node('th', 'Date'), node('th', 'Reports'));
  const thead = node('thead'); thead.append(head); table.append(thead);
  const body = node('tbody');
  for (const day of days) { const row = node('tr'); row.append(node('td', day.date), node('td', day.count)); body.append(row); }
  table.append(body); disclosure.append(table); group.append(disclosure);
  return group;
}
function categoryChart(counts) {
  const group = node('div', undefined, 'stat-group'); group.append(node('h2', 'Reports by category'));
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const highest = entries[0]?.[1] || 1;
  if (entries.length) {
    const leaders = entries.filter((entry) => entry[1] === highest).map(([key]) => types[key] || 'Unclassified');
    group.append(node('p', `Most reported: ${leaders.join(', ')} (${highest})`));
  } else group.append(node('p', 'No reports in this period.'));
  for (const [key, count] of entries) {
    const label = node('p', `${types[key] || 'Unclassified'}: ${count}`, 'bar-label');
    const track = node('div', undefined, 'bar-track'); const bar = node('div', undefined, 'bar-fill');
    bar.style.width = `${count / highest * 100}%`; bar.style.backgroundColor = colors[key] || '#586773';
    track.setAttribute('aria-hidden', 'true'); track.append(bar); group.append(label, track);
  }
  return group;
}
let statisticsVersion = 0;
async function loadStatistics() {
  const version = ++statisticsVersion;
  const data = await api(`/statistics?days=${$('stats-days').value}`);
  if (version !== statisticsVersion) return;
  const cards = node('div', undefined, 'stats-cards');
  for (const [label, value] of [
    ['Report records', data.reports.total], ['With images', data.reports.with_image],
    ['With locations', data.reports.with_location], ['With both', data.reports.with_both],
    ['Without either', data.reports.without_media],
  ]) {
    const card = node('div', undefined, 'stat-card');
    card.append(node('span', label), node('strong', value)); cards.append(card);
  }
  const groups = node('div', undefined, 'stats-groups');
  groups.append(categoryChart(data.reports.by_type), countTable('Sessions by analysis status (all time)', data.sessions.by_status));
  const allTime = node('p', `All time: ${data.users.total} users · ${data.sessions.total} sessions · ${data.images.total} images received · ${data.locations.total} locations received`, 'muted');
  $('statistics').replaceChildren(
    node('p', `Reports from the last ${data.period_days} calendar days. “With images” and “With locations” each include reports with both.`, 'muted'),
    cards, dailyChart(data.reports.by_day), groups, allTime,
    node('p', `Updated ${new Date().toLocaleTimeString()}`, 'muted'),
  );
}
async function loadUsers() {
  const data = await api(`/users?limit=${PAGE_SIZE}&offset=${usersOffset}`);
  if (!usersLoaded) $('user-list').replaceChildren();
  for (const user of data.items) {
    const label = node('label');
    const input = node('input'); input.type = 'checkbox'; input.value = user.id;
    label.append(input, document.createTextNode(` ${user.name || user.line_user_id}`));
    $('user-list').append(label);
  }
  usersLoaded = true; usersOffset += data.items.length;
  $('more-users').hidden = usersOffset >= data.total;
  if (!usersOffset) $('user-list').append(node('p', 'No known users yet.'));
}
async function loadBroadcasts(reset = true) {
  const offset = reset ? 0 : broadcastOffset;
  const data = await api(`/broadcasts?limit=${PAGE_SIZE}&offset=${offset}`);
  let body;
  if (reset) {
    const table = node('table');
    const head = node('tr');
    for (const title of ['Message', 'Recipients', 'Status', 'Created']) head.append(node('th', title));
    const thead = node('thead'); thead.append(head); table.append(thead);
    body = node('tbody'); body.id = 'broadcast-rows'; table.append(body);
    $('broadcast-history').replaceChildren(table);
  } else body = $('broadcast-rows');
  for (const item of data.items) {
    const row = node('tr'); const cell = node('td');
    const button = node('button', item.text.length > 80 ? `${item.text.slice(0, 80)}…` : item.text);
    button.type = 'button';
    button.addEventListener('click', () => guarded(button, () => showBroadcast(item.id)));
    cell.append(button);
    row.append(cell, node('td', item.recipient_count), node('td', item.status), node('td', date(item.created_at)));
    body.append(row);
  }
  broadcastOffset = offset + data.items.length;
  $('more-broadcasts').hidden = broadcastOffset >= data.total;
  if (!broadcastOffset) $('broadcast-history').replaceChildren(node('p', 'No broadcasts yet.'));
}
function renderBroadcast(item) {
  const panel = $('broadcast-detail');
  panel.replaceChildren(node('h2', 'Saved message'), node('p', item.text, 'message-text'));
  const fields = node('dl');
  field(fields, 'Audience', item.audience === 'all' ? 'All known users at draft creation' : 'Selected users');
  field(fields, 'Recipients', item.recipient_count);
  field(fields, 'Status', item.status);
  for (const [status, count] of Object.entries(item.counts || {})) field(fields, status, count);
  panel.append(fields);
  if (item.status === 'draft') {
    const send = node('button', `Send to ${item.recipient_count} recipient(s)`, 'send-button');
    send.type = 'button'; send.disabled = !item.recipient_count;
    send.addEventListener('click', () => guarded(send, async () => {
      await api(`/broadcasts/${item.id}/send`, { method: 'POST' });
      notice('Sending started. The status below will update automatically.');
      await showBroadcast(item.id); await loadBroadcasts();
    }));
    panel.append(send);
  }
  if (item.counts?.unknown) panel.append(node('p', 'Some requests have an unknown outcome. They will not be resent automatically.'));
  if (item.recipients?.length) {
    const disclosure = node('details'); disclosure.append(node('summary', 'Recipient status'));
    const table = node('table');
    const head = node('tr'); head.append(node('th', 'User'), node('th', 'Status'));
    const thead = node('thead'); thead.append(head); table.append(thead);
    const body = node('tbody');
    for (const recipient of item.recipients) {
      const row = node('tr'); row.append(node('td', recipient.user_id), node('td', recipient.status)); body.append(row);
    }
    table.append(body); disclosure.append(table); panel.append(disclosure);
  }
}
async function showBroadcast(id) {
  selectedBroadcast = id;
  clearTimeout(pollTimer);
  const item = await api(`/broadcasts/${id}`);
  if (selectedBroadcast !== id) return;
  renderBroadcast(item);
  if (item.status === 'sending' && location.hash === '#broadcasts') {
    pollTimer = setTimeout(() => guarded(null, async () => { await showBroadcast(id); await loadBroadcasts(); }), 2000);
  }
}
async function route() {
  const page = ['map', 'dashboard', 'broadcasts'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'map';
  clearTimeout(pollTimer);
  notice('');
  for (const section of document.querySelectorAll('main > section')) section.hidden = section.id !== `page-${page}`;
  for (const link of document.querySelectorAll('nav a')) {
    if (link.hash === `#${page}`) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (page === 'map') { createMap(); map?.invalidateSize(); await loadReports(); }
  if (page === 'dashboard') await loadStatistics();
  if (page === 'broadcasts') {
    const settings = await api('/broadcast-settings');
    $('auto-status').textContent = `Automatic broadcasts: ${settings.auto_enabled ? 'enabled' : 'disabled'}`;
    await loadBroadcasts();
    if (selectedBroadcast) await showBroadcast(selectedBroadcast);
  }
}
$('refresh-reports').addEventListener('click', (event) => guarded(event.currentTarget, () => loadReports()));
$('load-more').addEventListener('click', (event) => guarded(event.currentTarget, () => loadReports(false)));
$('type-filter').addEventListener('change', () => guarded(null, () => loadReports()));
$('refresh-stats').addEventListener('click', (event) => guarded(event.currentTarget, loadStatistics));
$('stats-days').addEventListener('change', () => guarded(null, loadStatistics));
$('audience').addEventListener('change', () => {
  $('user-picker').hidden = $('audience').value !== 'selected';
  if (!$('user-picker').hidden && !usersLoaded) guarded(null, loadUsers);
});
$('more-users').addEventListener('click', (event) => guarded(event.currentTarget, loadUsers));
$('refresh-broadcasts').addEventListener('click', (event) => guarded(event.currentTarget, async () => {
  await loadBroadcasts(); if (selectedBroadcast) await showBroadcast(selectedBroadcast);
}));
$('more-broadcasts').addEventListener('click', (event) => guarded(event.currentTarget, () => loadBroadcasts(false)));
$('broadcast-form').addEventListener('submit', (event) => {
  event.preventDefault();
  guarded($('create-draft'), async () => {
    const audience = $('audience').value;
    const user_ids = audience === 'selected' ? [...document.querySelectorAll('#user-list input:checked')].map((input) => input.value) : [];
    if (audience === 'selected' && !user_ids.length) throw new Error('Select at least one recipient.');
    const item = await api('/broadcasts', { method: 'POST', body: JSON.stringify({ text: $('broadcast-text').value, audience, user_ids }) });
    notice('Draft saved. Review the message and recipient count before sending.');
    await showBroadcast(item.id); await loadBroadcasts();
  });
});
window.addEventListener('hashchange', () => guarded(null, route));
guarded(null, route);
