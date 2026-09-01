const status = document.getElementById('status');
const cards = document.getElementById('cards');
const dateFrom = document.getElementById('dateFrom');
const dateTo = document.getElementById('dateTo');
const locationFilter = document.getElementById('locationFilter');
const distanceMin = document.getElementById('distanceMin');
const distanceMax = document.getElementById('distanceMax');
const surfaceFilter = document.getElementById('surfaceFilter');
const applyFilter = document.getElementById('applyFilter');
const resetFilter = document.getElementById('resetFilter');

let races = [];

function toNumber(value) {
  if (typeof value !== 'string') return NaN;
  return Number(value.replace(',', '.'));
}

function parseDistanceValues(raw) {
  if (!raw) return [];
  const text = raw.replace(/\u00a0/g, ' ').replace(/–/g, '-').toLowerCase();
  const values = new Set();

  for (const match of text.matchAll(/(\d+[.,]?\d*)\s*km/g)) {
    values.add(toNumber(match[1]));
  }
  for (const match of text.matchAll(/(\d+[.,]?\d*)\s*m\b/g)) {
    const km = toNumber(match[1]) / 1000;
    if (!Number.isNaN(km)) values.add(km);
  }
  for (const match of text.matchAll(/(\d+[.,]?\d*)\s*míle(?:.*?\((\d+[.,]?\d*)\s*km\))?/g)) {
    if (match[2]) {
      values.add(toNumber(match[2]));
    } else {
      values.add(toNumber(match[1]) * 1.609);
    }
  }
  if (values.size === 0) {
    for (const match of text.matchAll(/(\d+[.,]?\d*)/g)) {
      values.add(toNumber(match[1]));
    }
  }

  return [...values].filter(v => !Number.isNaN(v)).sort((a, b) => a - b);
}

function normalizeSurfaces(raw) {
  if (!raw) return [];
  return raw
    .replace(/[+\/]/g, ',')
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter(Boolean);
}

function getDisplaySurface(raw) {
  if (!raw) return '–';
  return raw
    .split(/[+,\/]/)
    .map(part => part.trim())
    .filter(Boolean)
    .join(' / ');
}

function normalizeRace(r) {
  if (r.info && typeof r.info === 'object') return r;
  const info = {
    'Dĺžka trate': r.dlzka ?? r['dlzka'] ?? r['Dĺžka trate'] ?? '',
    'Povrch': r.povrch ?? r['povrch'] ?? r['Povrch'] ?? '',
    'Štart': r.start_cas ?? r['start_cas'] ?? r['Štart'] ?? '',
    'Miesto': r.miesto ?? r['miesto'] ?? r.mesto ?? '',
    'Organizátor': r.organizator ?? r['organizator'] ?? r['Organizátor'] ?? '',
    'Informácie': r.popis ?? r['popis'] ?? (r.zdroj ? `Zdroj: ${r.zdroj}` : r['Informácie'] ?? '')
  };
  return { ...r, info, tags: r.tags ?? r.tagy ?? [] };
}

function hasUnknownDistanceTag(r) {
  const tags = r.tags ?? r.tagy ?? [];
  if (!Array.isArray(tags)) return false;
  return tags.some(tag => {
    if (!tag || typeof tag !== 'string') return false;
    const normalized = tag.replace(/_/g, ' ').toLowerCase().trim();
    return normalized === 'neznama dlzka';
  });
}

function isDistanceFilterActive(minKm, maxKm) {
  return !Number.isNaN(minKm) || !Number.isNaN(maxKm);
}

function getSurfaceOptions(races) {
  const set = new Set();
  races.forEach(r => {
    const value = r.info?.['Povrch'];
    if (value) normalizeSurfaces(value).forEach(item => set.add(item));
  });
  return [...set].sort();
}

function normalizeText(raw) {
  return raw
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractLocationKey(raw) {
  if (!raw) return '';
  const text = raw.split(',')[0].split('(')[0].replace(/-/g, ' ').trim();
  return normalizeText(text);
}

const REGION_PATTERNS = [
  ['bratislava', 'Bratislavský kraj'],
  ['kvetoslavov', 'Trnavský kraj'],
  ['trnava', 'Trnavský kraj'],
  ['piestany', 'Trnavský kraj'],
  ['ilava', 'Trenčiansky kraj'],
  ['dubnica', 'Trenčiansky kraj'],
  ['nove mesto n vahom', 'Trenčiansky kraj'],
  ['povazska', 'Trenčiansky kraj'],
  ['nitra', 'Nitriansky kraj'],
  ['komarno', 'Nitriansky kraj'],
  ['tlmace', 'Nitriansky kraj'],
  ['zilina', 'Žilinský kraj'],
  ['cadca', 'Žilinský kraj'],
  ['martin', 'Žilinský kraj'],
  ['dolny kubin', 'Žilinský kraj'],
  ['kysucke nove mesto', 'Žilinský kraj'],
  ['ruzomberok', 'Žilinský kraj'],
  ['banska bystrica', 'Banskobystrický kraj'],
  ['banska bysatrica', 'Banskobystrický kraj'],
  ['banska stiavnica', 'Banskobystrický kraj'],
  ['ziar nad hronom', 'Banskobystrický kraj'],
  ['krupina', 'Banskobystrický kraj'],
  ['lucenec', 'Banskobystrický kraj'],
  ['cierny balog', 'Banskobystrický kraj'],
  ['presov', 'Prešovský kraj'],
  ['poprad', 'Prešovský kraj'],
  ['levoca', 'Prešovský kraj'],
  ['vysoke tatry', 'Prešovský kraj'],
  ['nova lesna', 'Prešovský kraj'],
  ['strba', 'Prešovský kraj'],
  ['liptovska teplicka', 'Prešovský kraj'],
  ['mlynceky', 'Prešovský kraj'],
  ['paca', 'Prešovský kraj'],
  ['lutina', 'Prešovský kraj'],
  ['kosice', 'Košický kraj'],
  ['kos', 'Košický kraj'],
  ['kechnec', 'Košický kraj'],
  ['medzev', 'Košický kraj'],
  ['vysna mysla', 'Košický kraj'],
  ['opalove bane', 'Košický kraj'],
  ['dubnik', 'Košický kraj'],
  ['dobsinska', 'Košický kraj']
];

function inferRegion(r) {
  const candidates = [r.mesto, r.info?.Miesto, r.nazov].filter(Boolean);
  for (const candidate of candidates) {
    const key = extractLocationKey(candidate);
    if (key && typeof MUNICIPALITY_REGION_MAP !== 'undefined' && MUNICIPALITY_REGION_MAP[key]) {
      return MUNICIPALITY_REGION_MAP[key];
    }
  }

  const text = normalizeText([r.mesto, r.info?.Miesto, r.nazov, r.url].filter(Boolean).join(' '));
  for (const [pattern, region] of REGION_PATTERNS) {
    if (text.includes(pattern)) return region;
  }
  return null;
}

function getLocationFilterValues() {
  if (!locationFilter) return [];
  return Array.from(locationFilter.querySelectorAll('input[type="checkbox"]:checked'))
    .map(input => input.value.trim().toLowerCase())
    .filter(Boolean);
}

function renderLocationOptions(races) {
  if (!locationFilter) return;
  const set = new Set();
  races.forEach(r => {
    const region = inferRegion(r);
    if (region) set.add(region);
  });
  const options = [...set].sort((a, b) => a.localeCompare(b, 'sk', { sensitivity: 'base' }));
  locationFilter.innerHTML = '';
  options.forEach(value => {
    const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    const wrapper = document.createElement('label');
    wrapper.className = 'checkbox-item';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = value;
    input.id = `region-${slug}`;
    const span = document.createElement('span');
    span.textContent = value;
    wrapper.appendChild(input);
    wrapper.appendChild(span);
    locationFilter.appendChild(wrapper);
  });
}

function renderSurfaces(options) {
  surfaceFilter.innerHTML = '';
  options.forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value.charAt(0).toUpperCase() + value.slice(1);
    surfaceFilter.appendChild(option);
  });
}

function formatDate(dateString) {
  if (!dateString) return '–';
  const date = new Date(dateString + 'T00:00');
  return date.toLocaleDateString('sk-SK', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function renderRow(race) {
  const distance = race.info?.['Dĺžka trate'] || '–';
  const surface = getDisplaySurface(race.info?.['Povrch']);
  const place = race.mesto || '–';
  const start = race.info?.['Štart'] || '–';
  const region = inferRegion(race) || '–';

  return `<tr>
    <td class="td-date">${formatDate(race.datum)}</td>
    <td class="td-name"><a href="${race.url}" target="_blank" rel="noopener">${race.nazov}</a></td>
    <td>${place}</td>
    <td class="col-optional">${region}</td>
    <td>${distance}</td>
    <td class="col-optional">${surface}</td>
    <td class="col-optional">${start}</td>
  </tr>`;
}

function renderTable(rows) {
  if (!rows.length) return '<p class="note">Žiadne preteky nespĺňajú zadané kritériá.</p>';
  return `<table class="race-table">
    <thead>
      <tr>
        <th>Dátum</th>
        <th>Názov</th>
        <th>Mesto</th>
        <th class="col-optional">Kraj</th>
        <th>Dĺžka</th>
        <th class="col-optional">Povrch</th>
        <th class="col-optional">Štart</th>
      </tr>
    </thead>
    <tbody>${rows.map(renderRow).join('')}</tbody>
  </table>`;
}

function intersectsDistance(rangeValues, min, max) {
  if (!rangeValues.length) return Number.isNaN(min) && Number.isNaN(max);
  if (Number.isNaN(min) && Number.isNaN(max)) return true;
  const actualMin = Math.min(...rangeValues);
  const actualMax = Math.max(...rangeValues);
  if (!Number.isNaN(min) && actualMax < min) return false;
  if (!Number.isNaN(max) && actualMin > max) return false;
  return true;
}

function applyFilters() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const from = dateFrom.value ? new Date(dateFrom.value + 'T00:00') : today;
  const to = dateTo.value ? new Date(dateTo.value + 'T23:59:59') : null;
  const selectedRegions = getLocationFilterValues();
  const minKm = distanceMin.value ? Number(distanceMin.value) : NaN;
  const maxKm = distanceMax.value ? Number(distanceMax.value) : NaN;
  const selectedSurfaces = Array.from(surfaceFilter.selectedOptions).map(opt => opt.value.toLowerCase());

  const filtered = races.filter(r => {
    const raceDate = r.datum ? new Date(r.datum + 'T00:00') : null;
    if (!raceDate) return false;
    if (raceDate < from) return false;
    if (to && raceDate > to) return false;

    const region = inferRegion(r);
    if (selectedRegions.length && (!region || !selectedRegions.includes(region.toLowerCase()))) return false;

    const isDistanceActive = isDistanceFilterActive(minKm, maxKm);
    if (isDistanceActive && !hasUnknownDistanceTag(r)) {
      const distances = parseDistanceValues(r.info?.['Dĺžka trate'] || '');
      if (!intersectsDistance(distances, minKm, maxKm)) return false;
    }

    if (selectedSurfaces.length) {
      const raceSurfaces = normalizeSurfaces(r.info?.['Povrch'] || '');
      if (!selectedSurfaces.some(surface => raceSurfaces.includes(surface))) return false;
    }

    return true;
  });

  status.textContent = `${filtered.length} pretekov z ${races.length} zodpovedá filtru.`;
  cards.innerHTML = renderTable(filtered);
}

function resetFilters() {
  dateFrom.value = '';
  dateTo.value = '';
  Array.from(locationFilter.querySelectorAll('input[type="checkbox"]')).forEach(input => input.checked = false);
  distanceMin.value = '';
  distanceMax.value = '';
  Array.from(surfaceFilter.options).forEach(option => option.selected = false);
  applyFilters();
}

function loadRacesFromJson(data) {
  try {
    races = [...data].map(normalizeRace).sort((a, b) => {
      if (!a.datum) return 1;
      if (!b.datum) return -1;
      return a.datum.localeCompare(b.datum);
    });
    if (!dateFrom.value) {
      const today = new Date();
      dateFrom.value = formatDateInput(today);
    }
    renderLocationOptions(races);
    const surfaces = getSurfaceOptions(races);
    renderSurfaces(surfaces);
    status.textContent = `${races.length} pretekov načítaných.`;
    applyFilters();
  } catch (error) {
    status.textContent = 'Neplatný JSON súbor. Skontroluj obsah `data/all_preteky_norm.json`.';
    cards.innerHTML = `<p class="note">${error.message}</p>`;
  }
}

const DATA_URL = 'data/all_preteky_norm.json';

async function loadData() {
  status.textContent = `Načítavam ${DATA_URL}…`;
  try {
    const response = await fetch(DATA_URL);
    if (!response.ok) throw new Error(`HTTP ${response.status} – ${DATA_URL} nenájdený`);
    loadRacesFromJson(await response.json());
  } catch (error) {
    status.textContent = `Nepodarilo sa načítať ${DATA_URL}.`;
    // file:// blokuje fetch kvôli CORS — stránka musí bežať cez HTTP server
    const note = location.protocol === 'file:'
      ? 'Stránka je otvorená cez <code>file://</code>, kde prehliadač fetch blokuje. '
        + 'Spusť v adresári projektu <code>python3 -m http.server 8000</code> '
        + 'a otvor <code>http://localhost:8000/</code>.'
      : `Skontroluj, či <code>${DATA_URL}</code> existuje a je čitateľný.`;
    cards.innerHTML = `<p class="note">${note}<br/><br/>${error.message}</p>`;
  }
}

applyFilter.addEventListener('click', applyFilters);
resetFilter.addEventListener('click', resetFilters);

const filterToggle = document.getElementById('filterToggle');
const panelBody = document.getElementById('panelBody');
if (filterToggle && panelBody) {
  filterToggle.addEventListener('click', () => {
    const open = panelBody.classList.toggle('is-open');
    filterToggle.setAttribute('aria-expanded', open);
  });
}

loadData();

fetch('data/last_update.txt')
  .then(r => r.ok ? r.text() : null)
  .then(ts => {
    if (!ts) return;
    const d = new Date(ts.trim());
    if (!isNaN(d)) {
      document.getElementById('lastUpdate').textContent =
        'Posledná aktualizácia: ' + d.toLocaleDateString('sk-SK') + ' ' + d.toLocaleTimeString('sk-SK', { hour: '2-digit', minute: '2-digit' });
    }
  })
  .catch(() => {});
