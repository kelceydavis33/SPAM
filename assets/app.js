/* SPAM site — tabs, data loading, and the filter coverage plot. */

/* ── Filter definitions ─────────────────────────────────────────
   Pivot wavelengths and bandwidths in microns, from the nominal
   NIRCam filter list. Edit these if you want exact values.        */

const SPAM_FILTERS = [
  { name: "F070W", pivot: 0.704, width: 0.128 },
  { name: "F140M", pivot: 1.404, width: 0.142 },
  { name: "F162M", pivot: 1.626, width: 0.168 },
  { name: "F182M", pivot: 1.845, width: 0.238 },
  { name: "F210M", pivot: 2.093, width: 0.205 },
  { name: "F300M", pivot: 2.996, width: 0.318 },
  { name: "F335M", pivot: 3.365, width: 0.347 },
  { name: "F360M", pivot: 3.621, width: 0.372 },
  { name: "F430M", pivot: 4.280, width: 0.228 },
  { name: "F480M", pivot: 4.815, width: 0.303 }
];

const CEERS_FILTERS = [
  { name: "F115W", pivot: 1.154, width: 0.225 },
  { name: "F150W", pivot: 1.501, width: 0.318 },
  { name: "F200W", pivot: 1.990, width: 0.461 },
  { name: "F277W", pivot: 2.786, width: 0.672 },
  { name: "F356W", pivot: 3.563, width: 0.787 },
  { name: "F410M", pivot: 4.092, width: 0.436 },
  { name: "F444W", pivot: 4.421, width: 1.024 }
];

/* ── Tabs ───────────────────────────────────────────────────── */

const tabs = Array.from(document.querySelectorAll(".tab"));

function showPanel(name) {
  let found = false;
  for (const tab of tabs) {
    const isActive = tab.dataset.panel === name;
    if (isActive) found = true;
    tab.setAttribute("aria-selected", isActive);
    tab.tabIndex = isActive ? 0 : -1;
    document.getElementById("panel-" + tab.dataset.panel).hidden = !isActive;
  }
  if (!found) showPanel("overview");
}

function panelFromHash() {
  const name = window.location.hash.replace("#", "");
  const known = tabs.some(tab => tab.dataset.panel === name);
  return known ? name : "overview";
}

for (const tab of tabs) {
  tab.addEventListener("click", () => {
    window.location.hash = tab.dataset.panel;
  });
}

// Left/right arrows move between tabs, which is what screen reader users expect.
document.querySelector(".tabs").addEventListener("keydown", event => {
  if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
  const current = tabs.findIndex(tab => tab.getAttribute("aria-selected") === "true");
  const step = event.key === "ArrowRight" ? 1 : -1;
  const next = tabs[(current + step + tabs.length) % tabs.length];
  window.location.hash = next.dataset.panel;
  next.focus();
});

window.addEventListener("hashchange", () => showPanel(panelFromHash()));
showPanel(panelFromHash());

/* ── Coverage plot ──────────────────────────────────────────── */

// Wavelength to colour, interpolating across the five ramp stops in the CSS
// so that neighbouring filters never come out the same colour.
function bandColor(wavelength) {
  const styles = getComputedStyle(document.documentElement);
  const stops = ["--wl-1", "--wl-2", "--wl-3", "--wl-4", "--wl-5"].map(name => {
    const hex = styles.getPropertyValue(name).trim();
    return [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16)
    ];
  });

  let fraction = (Math.log10(wavelength) - Math.log10(0.65)) / (Math.log10(5.2) - Math.log10(0.65));
  fraction = Math.min(Math.max(fraction, 0), 1);

  const position = fraction * (stops.length - 1);
  const lower = Math.min(Math.floor(position), stops.length - 2);
  const weight = position - lower;

  const red   = Math.round(stops[lower][0] + weight * (stops[lower + 1][0] - stops[lower][0]));
  const green = Math.round(stops[lower][1] + weight * (stops[lower + 1][1] - stops[lower][1]));
  const blue  = Math.round(stops[lower][2] + weight * (stops[lower + 1][2] - stops[lower][2]));

  return `rgb(${red}, ${green}, ${blue})`;
}

function drawCoverage() {
  const host = document.getElementById("coverage-plot");
  if (!host) return;

  const width = 1000;
  const height = 200;
  const left = 10;
  const right = width - 10;
  const baseline = height - 40;
  const barHeight = 62;

  const minWl = 0.62;
  const maxWl = 5.3;

  function xFor(wavelength) {
    const fraction = (Math.log10(wavelength) - Math.log10(minWl)) / (Math.log10(maxWl) - Math.log10(minWl));
    return left + fraction * (right - left);
  }

  let svg = `<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" role="img" `;
  svg += `aria-label="Wavelength coverage of the ten SPAM filters compared with existing CEERS filters, 0.7 to 4.8 microns">`;

  // CEERS bands sit behind, as a flat grey reference row.
  for (const filter of CEERS_FILTERS) {
    const x0 = xFor(filter.pivot - filter.width / 2);
    const x1 = xFor(filter.pivot + filter.width / 2);
    svg += `<g class="band">`;
    svg += `<rect x="${x0}" y="${baseline - 24}" width="${x1 - x0}" height="18" fill="#D6D8DC" rx="1"/>`;
    svg += `<text class="band__label" x="${(x0 + x1) / 2}" y="${baseline - 11}" text-anchor="middle">${filter.name}</text>`;
    svg += `</g>`;
  }

  // SPAM bands sit above, all the same height. Only the horizontal extent
  // carries information, so nothing else is scaled.
  for (const filter of SPAM_FILTERS) {
    const x0 = xFor(filter.pivot - filter.width / 2);
    const x1 = xFor(filter.pivot + filter.width / 2);
    const centre = (x0 + x1) / 2;
    const y = baseline - 30 - barHeight;
    const color = bandColor(filter.pivot);

    svg += `<g class="band">`;
    svg += `<rect x="${x0}" y="${y}" width="${x1 - x0}" height="${barHeight}" fill="${color}" rx="1"/>`;
    svg += `<text class="band__label band__label--spam" x="${centre}" y="${y - 8}" text-anchor="start" `;
    svg += `transform="rotate(-90 ${centre} ${y - 8})">${filter.name}</text>`;
    svg += `<title>${filter.name} — pivot ${filter.pivot} \u00B5m, width ${filter.width} \u00B5m</title>`;
    svg += `</g>`;
  }

  // Axis.
  svg += `<line class="axis__line" x1="${left}" y1="${baseline}" x2="${right}" y2="${baseline}"/>`;
  for (const tick of [0.7, 1, 1.5, 2, 3, 4, 5]) {
    const x = xFor(tick);
    svg += `<line class="axis__line" x1="${x}" y1="${baseline}" x2="${x}" y2="${baseline + 5}"/>`;
    svg += `<text class="axis__label" x="${x}" y="${baseline + 18}" text-anchor="middle">${tick}</text>`;
  }
  svg += `<text class="axis__label" x="${right}" y="${baseline + 34}" text-anchor="end">wavelength (\u00B5m)</text>`;
  svg += `</svg>`;

  host.innerHTML = svg;
}

drawCoverage();

/* ── Data loading ───────────────────────────────────────────── */

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text === undefined || text === null ? "" : text;
  return div.innerHTML;
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(path + " returned " + response.status);
  return response.json();
}

function showError(host, path) {
  host.innerHTML = `<p class="status">Could not load ${escapeHtml(path)}. `
    + `If you are opening index.html directly from disk, run a local server instead.</p>`;
}

function showEmpty(host, message) {
  host.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
}

/* Catalogs */
async function renderCatalogs() {
  const host = document.getElementById("catalog-list");
  let items;
  try {
    items = await loadJson("data/catalogs.json");
  } catch (error) {
    showError(host, "data/catalogs.json");
    return;
  }

  if (items.length === 0) {
    showEmpty(host, "No catalogs released yet. First data release expected 2025/2026.");
    return;
  }

  let html = "";
  for (const item of items) {
    html += `<article class="card">`;
    html += `<div class="card__head">`;
    html += `<h2 class="card__title">${escapeHtml(item.name)}</h2>`;
    html += `<span class="card__meta">${escapeHtml(item.version)} · ${escapeHtml(item.released)} · ${escapeHtml(item.size)}</span>`;
    html += `</div>`;
    html += `<p class="card__body">${escapeHtml(item.description)}</p>`;
    html += `<div class="chips">`;
    if (item.download) html += `<a class="chip chip--download" href="${escapeHtml(item.download)}">Download ${escapeHtml(item.format)}</a>`;
    if (item.doi)      html += `<a class="chip" href="${escapeHtml(item.doi)}">DOI</a>`;
    if (item.readme)   html += `<a class="chip" href="${escapeHtml(item.readme)}">Column descriptions</a>`;
    html += `</div></article>`;
  }
  host.innerHTML = html;
}

/* Team */
async function renderTeam() {
  const host = document.getElementById("team-list");
  let groups;
  try {
    groups = await loadJson("data/team.json");
  } catch (error) {
    showError(host, "data/team.json");
    return;
  }

  let html = "";
  for (const group of groups) {
    html += `<section class="team-group">`;
    html += `<h2 class="team-group__name">${escapeHtml(group.group)}</h2>`;
    html += `<div class="team-grid">`;
    for (const member of group.members) {
      html += `<article class="card">`;
      html += `<p class="member__name">${escapeHtml(member.name)}</p>`;
      html += `<p class="member__role">${escapeHtml(member.role)}</p>`;
      html += `<p class="member__inst">${escapeHtml(member.institution)}</p>`;
      html += `<p class="member__links">`;
      if (member.website) html += `<a href="${escapeHtml(member.website)}">Website</a>`;
      if (member.orcid)   html += `<a href="https://orcid.org/${escapeHtml(member.orcid)}">ORCID</a>`;
      html += `</p></article>`;
    }
    html += `</div></section>`;
  }
  host.innerHTML = html;
}

/* Team papers */
async function renderPapers() {
  const host = document.getElementById("paper-list");
  let items;
  try {
    items = await loadJson("data/papers.json");
  } catch (error) {
    showError(host, "data/papers.json");
    return;
  }

  if (items.length === 0) {
    showEmpty(host, "No team papers listed yet.");
    return;
  }

  let html = "";
  for (const item of items) {
    html += `<article class="card">`;
    html += `<div class="card__head">`;
    html += `<h2 class="card__title"><a href="${escapeHtml(item.url)}">${escapeHtml(item.title)}</a></h2>`;
    html += `<span class="card__meta">${escapeHtml(item.year)} · ${escapeHtml(item.journal)}</span>`;
    html += `</div>`;
    html += `<p class="card__authors">${escapeHtml(item.authors)}</p>`;
    html += `</article>`;
  }
  host.innerHTML = html;
}

/* arXiv feed */
async function renderArxiv() {
  const host = document.getElementById("arxiv-list");
  const stamp = document.getElementById("arxiv-stamp");
  let feed;
  try {
    feed = await loadJson("data/arxiv.json");
  } catch (error) {
    showError(host, "data/arxiv.json");
    return;
  }

  if (feed.generated_at) {
    const when = new Date(feed.generated_at);
    const scope = feed.full_text_search ? "arXiv abstracts + ADS full text" : "arXiv abstracts only";
    stamp.textContent = "Last checked " + when.toISOString().slice(0, 10) + " \u00B7 " + scope;
  }

  if (feed.papers.length === 0) {
    showEmpty(host, "No matching preprints yet. The collector runs every Monday.");
    return;
  }

  let html = "";
  for (const paper of feed.papers) {
    // ADS hits without an arXiv posting are keyed by bibcode, which should not
    // be labelled as an arXiv number.
    const looksLikeArxivId = /^\d{4}\.\d{4,5}$/.test(paper.id);
    const label = looksLikeArxivId ? "arXiv:" + paper.id : paper.id;

    html += `<article class="card">`;
    html += `<div class="card__head">`;
    html += `<h2 class="card__title"><a href="${escapeHtml(paper.url)}">${escapeHtml(paper.title)}</a></h2>`;
    html += `<span class="card__meta">${escapeHtml(label)} · ${escapeHtml(paper.published.slice(0, 10))}</span>`;
    html += `</div>`;
    html += `<p class="card__authors">${escapeHtml(paper.authors)}</p>`;
    if (paper.source === "ads") {
      html += `<p class="card__note">Matched on full text, not the abstract.</p>`;
    }
    html += `</article>`;
  }
  host.innerHTML = html;
}

renderCatalogs();
renderTeam();
renderPapers();
renderArxiv();
