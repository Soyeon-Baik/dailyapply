/* DailyApply — Dashboard App */

const STATUS_KEY = 'dailyapply_status';
const MANUAL_KEY = 'dailyapply_manual';
const JOBS_URL   = 'jobs.json';

let allJobs = [];
let filteredJobs = [];

// ── Manual monitoring companies ───────────────────────────────────────────────
const MANUAL_COMPANIES = [
  { name: 'Microsoft',  url: 'https://jobs.careers.microsoft.com',                  domains: 'AI · Search · Cloud'          },
  { name: 'Amazon',     url: 'https://www.amazon.jobs',                             domains: 'E-commerce · Search · Cloud'  },
  { name: 'Google',     url: 'https://www.google.com/about/careers',                domains: 'Search · AI · Ads'            },
  { name: 'Meta',       url: 'https://www.metacareers.com/jobs',                    domains: 'AI · Discovery · Social'      },
  { name: 'TikTok',     url: 'https://lifeattiktok.com',                            domains: 'AI · Recommendation · Ecomm'  },
  { name: 'DoorDash',   url: 'https://careersatdoordash.com',                       domains: 'Marketplace · Logistics'      },
  { name: 'Uber',       url: 'https://www.uber.com/global/en/careers',              domains: 'Marketplace · Mobility'       },
  { name: 'eBay',       url: 'https://jobs.ebayinc.com/us',                         domains: 'Marketplace · Search'         },
  { name: 'Adobe',      url: 'https://careers.adobe.com',                           domains: 'Creative · AI · SaaS'         },
  { name: 'Expedia',    url: 'https://expedia.wd5.myworkdayjobs.com/search',        domains: 'Travel · Search · Consumer'   },
  { name: 'Zillow',     url: 'https://www.zillow.com/careers',                      domains: 'Real Estate · Search'         },
  { name: 'CVS',        url: 'https://jobs.cvshealth.com',                          domains: 'Health · Consumer'            },
  { name: 'Salesforce', url: 'https://www.salesforce.com/company/careers',          domains: 'CRM · AI · Enterprise'        },
  { name: 'Shopify',    url: 'https://www.shopify.com/careers',                     domains: 'E-commerce · Platform'        },
  { name: 'Cisco',      url: 'https://careers.cisco.com',                           domains: 'Networking · Security · Cloud'},
];

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  search: '',
  recommendation: 'all',
  sponsorship: 'all',
  location: 'all',
  priority: 'all',
  sort: 'score',
  minScore: 70,        // default: hide <70
  showLowScore: false, // toggle to reveal <70
  days: 'all',
  hideSkipped: false,
};

// ── localStorage helpers ──────────────────────────────────────────────────────
function getStatuses() {
  try { return JSON.parse(localStorage.getItem(STATUS_KEY) || '{}'); }
  catch { return {}; }
}
function getStatus(jobId) { return getStatuses()[jobId] || 'New'; }
function setStatus(jobId, status) {
  const store = getStatuses();
  store[jobId] = status;
  localStorage.setItem(STATUS_KEY, JSON.stringify(store));
}

function getManualStore() {
  try { return JSON.parse(localStorage.getItem(MANUAL_KEY) || '{}'); }
  catch { return {}; }
}
function getManualStatus(name) {
  const store = getManualStore();
  const checked = store[name];
  if (!checked) return null;
  const checkedDate = new Date(checked).toLocaleDateString();
  const todayDate   = new Date().toLocaleDateString();
  if (checkedDate !== todayDate) return null;
  return checked;
}
function setManualChecked(name) {
  const store = getManualStore();
  store[name] = new Date().toISOString();
  localStorage.setItem(MANUAL_KEY, JSON.stringify(store));
  renderManual();
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadJobs() {
  try {
    const res = await fetch(JOBS_URL + '?_=' + Date.now());
    allJobs = await res.json();
    const ts = new Date().toLocaleString();
    document.getElementById('lastUpdated').textContent = `Last updated: ${ts}`;
    applyFilters();
  } catch (e) {
    document.getElementById('jobList').innerHTML =
      `<div class="empty"><h3>Could not load jobs.json</h3>
       <p>Run the pipeline first, or open via a local server (not file://).</p></div>`;
  }
}

// ── Filter & sort ─────────────────────────────────────────────────────────────
function applyFilters() {
  const statuses = getStatuses();

  filteredJobs = allJobs.filter(job => {
    const status = statuses[job.id] || 'New';
    if (state.hideSkipped && status === 'Skip') return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      if (!job.title.toLowerCase().includes(q) &&
          !job.company.toLowerCase().includes(q)) return false;
    }
    if (state.recommendation !== 'all' && job.recommendation !== state.recommendation) return false;
    if (state.sponsorship    !== 'all' && job.sponsorship_status !== state.sponsorship) return false;
    if (state.location       !== 'all' && job.location_fit !== state.location) return false;
    if (state.priority       !== 'all' && job.company_priority !== state.priority) return false;
    // Score gate: unless showLowScore, hide <70
    if (!state.showLowScore && job.fit_score < state.minScore) return false;
    if (state.days !== 'all') {
      const maxDays = parseInt(state.days);
      if (job.days_old !== null && job.days_old > maxDays) return false;
    }
    return true;
  });

  // Sort: high-priority always floats to top, then user-selected secondary sort
  filteredJobs.sort((a, b) => {
    const highA = a.company_priority === 'high' ? 0 : 1;
    const highB = b.company_priority === 'high' ? 0 : 1;
    if (highA !== highB) return highA - highB;

    switch (state.sort) {
      case 'score':   return b.fit_score - a.fit_score;
      case 'newest':  return (a.days_old ?? 999) - (b.days_old ?? 999);
      case 'company': return a.company.localeCompare(b.company);
      case 'recommendation': {
        const order = { Apply: 0, Maybe: 1, Skip: 2 };
        return (order[a.recommendation] ?? 3) - (order[b.recommendation] ?? 3);
      }
      default: return 0;
    }
  });

  renderJobs();

  const hidden = allJobs.filter(j => !state.showLowScore && j.fit_score < state.minScore).length;
  const hiddenNote = hidden > 0 ? ` (${hidden} below 70 hidden)` : '';
  document.getElementById('resultsCount').textContent =
    `${filteredJobs.length} of ${allJobs.length} jobs${hiddenNote}`;
}

// ── Job card rendering ────────────────────────────────────────────────────────
function renderJobs() {
  const list = document.getElementById('jobList');
  if (!filteredJobs.length) {
    list.innerHTML = '<div class="empty"><h3>No jobs match your filters</h3><p>Try adjusting the filters above.</p></div>';
    return;
  }
  list.innerHTML = filteredJobs.map(renderCard).join('');

  list.querySelectorAll('.status-select').forEach(sel => {
    sel.addEventListener('change', e => {
      const id = e.target.dataset.jobId;
      const status = e.target.value;
      setStatus(id, status);
      e.target.className = 'status-select status-' + status.toLowerCase();
      if (state.hideSkipped && status === 'Skip')
        e.target.closest('.job-card').remove();
    });
  });

  list.querySelectorAll('.coaching-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const coaching = btn.nextElementSibling;
      const open = coaching.classList.toggle('open');
      btn.textContent = open ? '▲ Hide coaching' : '▼ Show resume coaching';
    });
  });
}

function renderCard(job) {
  const status    = getStatus(job.id);
  const recClass  = { Apply: 'apply', Maybe: 'maybe', Skip: 'skip' }[job.recommendation] || 'maybe';
  const targetBadge   = job.company_priority === 'high'
    ? '<span class="badge badge-target">★ Target</span>' : '';
  const sponsorBadge  = renderSponsorBadge(job.sponsorship_status);
  const locBadge      = renderLocBadge(job.location_fit);

  const daysText  = job.days_old != null ? `${job.days_old}d ago` : 'Date unknown';
  const platform  = job.platform.charAt(0).toUpperCase() + job.platform.slice(1);
  const statusOptions = ['New', 'Saved', 'Applied', 'Skip']
    .map(s => `<option value="${s}"${s === status ? ' selected' : ''}>${s}</option>`).join('');

  return `
<div class="job-card" data-job-id="${esc(job.id)}">
  <div class="card-top">
    <div class="badges">
      <span class="badge badge-${recClass}">${job.recommendation}</span>
      ${targetBadge}${sponsorBadge}${locBadge}
    </div>
    <div class="score-pill"><span class="score-num">${job.fit_score}</span>/100</div>
  </div>

  <div class="card-title">
    <h2>${esc(job.title)} — ${esc(job.company)}</h2>
  </div>

  <div class="card-meta">
    <span>${esc(job.location)}</span>
    <span>·</span><span>${platform}</span>
    <span>·</span><span>${daysText}</span>
    <span>·</span>
    <a href="${esc(job.url)}" target="_blank" rel="noopener">View posting ↗</a>
  </div>

  <p class="rationale">"${esc(job.recommendation_reason)}"</p>

  <div class="breakdown">${renderBreakdown(job.score_breakdown)}</div>

  <button class="coaching-toggle">▼ Show resume coaching</button>
  <div class="coaching">${renderCoaching(job)}</div>

  <div class="card-actions">
    <a class="apply-btn" href="${esc(job.url)}" target="_blank" rel="noopener">Apply →</a>
    <select class="status-select status-${status.toLowerCase()}" data-job-id="${esc(job.id)}">
      ${statusOptions}
    </select>
  </div>
</div>`;
}

function renderBreakdown(bd) {
  if (!bd) return '';
  return [
    ['Requirements', bd.requirements_match, 25],
    ['Domain',       bd.domain_alignment,   25],
    ['Archetype',    bd.pm_archetype_fit,    20],
    ['Evidence',     bd.evidence_strength,   15],
    ['Seniority',    bd.seniority_fit,       10],
    ['Bonus',        bd.nice_to_have_bonus,   5],
  ].map(([label, val, max]) => `
    <div class="breakdown-row">
      <span class="breakdown-label">${label}</span>
      <div class="breakdown-bar-wrap">
        <div class="breakdown-bar" style="width:${Math.round(val/max*100)}%"></div>
      </div>
      <span class="breakdown-val">${val}/${max}</span>
    </div>`).join('');
}

function renderCoaching(job) {
  const keywords = (job.resume_keywords || [])
    .map(k => `<span class="keyword-chip">${esc(k)}</span>`).join('');
  const bullets = (job.top_bullets || []).map(b => `<li>${esc(b)}</li>`).join('');
  const gap = job.gap_handling
    ? `<div class="coaching-section"><div class="coaching-label">Gap note</div>
       <p class="gap-text">${esc(job.gap_handling)}</p></div>` : '';
  const seniority = job.seniority_level
    ? `<div class="coaching-section"><div class="coaching-label">Seniority signal</div>
       <p>${seniorityLabel(job.seniority_level)}</p></div>` : '';

  return `
    <div class="coaching-section">
      <div class="coaching-label">Keywords to include</div>
      <div class="keywords">${keywords || '<span style="color:var(--text-muted)">None suggested</span>'}</div>
    </div>
    <div class="coaching-section">
      <div class="coaching-label">Top bullets to lead with</div>
      <ul>${bullets || '<li style="color:var(--text-muted)">No specific bullets identified</li>'}</ul>
    </div>
    <div class="coaching-section">
      <div class="coaching-label">Suggested summary</div>
      <p class="summary-text">${esc(job.suggested_summary || '')}</p>
    </div>
    ${gap}${seniority}
    <div class="coaching-section">
      <div class="coaching-label">Score rationale</div>
      <p class="summary-text">${esc(job.score_rationale || '')}</p>
    </div>`;
}

function seniorityLabel(level) {
  return ({
    too_junior: '⬇ Too junior — you may be overqualified',
    target:     '✓ Matches your target level',
    stretch:    '↑ Stretch role — one level up, competitive but possible',
    too_senior: '⬆ Too senior — Director/VP level',
    unclear:    '? Level not clearly stated in JD',
  })[level] || level;
}

function renderSponsorBadge(s) {
  if (s === 'does_sponsor')     return '<span class="badge badge-sponsor">Sponsors Visa</span>';
  if (s === 'does_not_sponsor') return '<span class="badge badge-no-sponsor">No Sponsorship</span>';
  return '<span class="badge badge-unknown-sponsor">Sponsorship?</span>';
}
function renderLocBadge(f) {
  if (f === 'exact')  return '<span class="badge badge-exact">Exact Location</span>';
  if (f === 'remote') return '<span class="badge badge-remote">Remote</span>';
  return '<span class="badge badge-mismatch">Location Mismatch</span>';
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Manual monitoring ─────────────────────────────────────────────────────────
function renderManual() {
  const store = getManualStore();

  const html = MANUAL_COMPANIES.map(co => {
    const checkedIso = getManualStatus(co.name);
    const isDone     = !!checkedIso;

    let lastText = 'Never checked';
    if (store[co.name]) {
      const daysAgo = (Date.now() - new Date(store[co.name]).getTime()) / 86400000;
      if (isDone)             lastText = 'Checked today';
      else if (daysAgo < 2)  lastText = 'Checked yesterday — due again';
      else                   lastText = `Checked ${Math.floor(daysAgo)}d ago — due again`;
    }

    return `
<div class="manual-card${isDone ? ' checked' : ''}" data-name="${esc(co.name)}">
  <div class="manual-card-name">${esc(co.name)}</div>
  <div class="manual-card-domains">${esc(co.domains)}</div>
  <div class="manual-card-last">${lastText}</div>
  <div class="manual-card-actions">
    <button class="check-btn${isDone ? ' done' : ''}" onclick="setManualChecked('${esc(co.name)}')">
      ${isDone ? '✓ Checked' : 'Mark checked'}
    </button>
    <a class="career-btn" href="${esc(co.url)}" target="_blank" rel="noopener">Careers ↗</a>
  </div>
</div>`;
  }).join('');

  document.getElementById('manualGrid').innerHTML = html;
}

// ── Filter control wiring ─────────────────────────────────────────────────────
function wire() {
  document.getElementById('search').addEventListener('input', e => {
    state.search = e.target.value; applyFilters();
  });

  [['recommendation','recommendation'],['sponsorship','sponsorship'],
   ['locationFit','location'],['priority','priority'],['sortBy','sort']
  ].forEach(([id, key]) => {
    document.getElementById(id).addEventListener('change', e => {
      state[key] = e.target.value; applyFilters();
    });
  });

  document.getElementById('scoreRange').addEventListener('input', e => {
    state.minScore = parseInt(e.target.value);
    document.getElementById('scoreVal').textContent = e.target.value;
    applyFilters();
  });

  document.querySelectorAll('.days-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.days-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.days = btn.dataset.days;
      applyFilters();
    });
  });

  document.getElementById('hideSkipped').addEventListener('click', e => {
    state.hideSkipped = !state.hideSkipped;
    e.currentTarget.classList.toggle('active', state.hideSkipped);
    applyFilters();
  });

  document.getElementById('showLowScore').addEventListener('click', e => {
    state.showLowScore = !state.showLowScore;
    e.currentTarget.classList.toggle('active', state.showLowScore);
    e.currentTarget.textContent = state.showLowScore ? 'Hide <70 Score' : 'Show <70 Score';
    applyFilters();
  });
}

// ── Boot ──────────────────────────────────────────────────────────────────────
wire();
loadJobs();
renderManual();
