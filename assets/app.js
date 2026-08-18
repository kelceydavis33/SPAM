/* SPAM site — tabs, data loading, and the filter coverage plot. */

/* ── Filter definitions ─────────────────────────────────────────
   All values from the JWST NIRCam filter tables (JDox), based on
   commissioning flight data:
   https://jwst-docs.stsci.edu/jwst-near-infrared-camera/nircam-instrumentation/nircam-filters

   pivot = pivot wavelength, bw = bandwidth, blue/red = half-power
   wavelengths. All in microns. Bars are drawn between the half-power
   points; the tooltip reports the bandwidth.                         */

const SPAM_FILTERS = [
  { name: "F070W", pivot: 0.704, bw: 0.128, blue: 0.624, red: 0.781 },
  { name: "F140M", pivot: 1.404, bw: 0.142, blue: 1.331, red: 1.479, shared: true },
  { name: "F162M", pivot: 1.626, bw: 0.168, blue: 1.542, red: 1.713, shared: true },
  { name: "F182M", pivot: 1.845, bw: 0.238, blue: 1.722, red: 1.968, shared: true },
  { name: "F210M", pivot: 2.093, bw: 0.205, blue: 1.992, red: 2.201, shared: true },
  { name: "F300M", pivot: 2.996, bw: 0.318, blue: 2.831, red: 3.157 },
  { name: "F335M", pivot: 3.365, bw: 0.347, blue: 3.177, red: 3.537 },
  { name: "F360M", pivot: 3.621, bw: 0.372, blue: 3.426, red: 3.814 },
  { name: "F430M", pivot: 4.280, bw: 0.228, blue: 4.167, red: 4.398 },
  { name: "F480M", pivot: 4.834, bw: 0.303, blue: 4.662, red: 4.973 }
];

const CEERS_FILTERS = [
  { name: "F090W", pivot: 0.901, bw: 0.194, blue: 0.795, red: 1.005 },
  { name: "F115W", pivot: 1.154, bw: 0.225, blue: 1.013, red: 1.282 },
  { name: "F150W", pivot: 1.501, bw: 0.318, blue: 1.331, red: 1.668 },
  { name: "F200W", pivot: 1.990, bw: 0.461, blue: 1.755, red: 2.227 },
  { name: "F277W", pivot: 2.786, bw: 0.672, blue: 2.423, red: 3.132 },
  { name: "F356W", pivot: 3.563, bw: 0.787, blue: 3.135, red: 3.981 },
  { name: "F410M", pivot: 4.092, bw: 0.436, blue: 3.866, red: 4.302 },
  { name: "F444W", pivot: 4.421, bw: 1.024, blue: 3.881, red: 4.982 }
];

/* MINERVA (Cycle 4 treasury, GO 7814) images eight medium bands over
   AEGIS/CEERS. Six of them duplicate SPAM, so only the two it uniquely
   adds are shown here. Those two complete the full set of twelve NIRCam
   medium bands over this field, together with SPAM's nine and F410M
   from CEERS.                                                        */

const MINERVA_FILTERS = [
  { name: "F250M", pivot: 2.503, bw: 0.181, blue: 2.412, red: 2.595 },
  { name: "F460M", pivot: 4.624, bw: 0.228, blue: 4.515, red: 4.747 }
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
  const height = 210;
  const left = 10;
  const right = width - 10;
  const baseline = height - 40;
  const barHeight = 62;

  const minWl = 0.60;
  const maxWl = 5.3;

  function xFor(wavelength) {
    const fraction = (Math.log10(wavelength) - Math.log10(minWl)) / (Math.log10(maxWl) - Math.log10(minWl));
    return left + fraction * (right - left);
  }

  // Everything a bar needs to describe itself when hovered.
  function dataAttrs(filter, program) {
    return `data-name="${filter.name}" data-program="${program}" `
      + `data-pivot="${filter.pivot.toFixed(3)}" data-bw="${filter.bw.toFixed(3)}" `
      + `data-blue="${filter.blue.toFixed(3)}" data-red="${filter.red.toFixed(3)}"`;
  }

  let svg = `<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" role="img" `;
  svg += `aria-label="NIRCam wavelength coverage from 0.6 to 5 microns: ten SPAM filters, `;
  svg += `eight existing CEERS filters, and the two medium bands MINERVA adds">`;

  // CEERS bands sit low, as a flat grey reference row.
  for (const filter of CEERS_FILTERS) {
    const x0 = xFor(filter.blue);
    const x1 = xFor(filter.red);
    svg += `<g class="band" tabindex="0" ${dataAttrs(filter, "Existing CEERS coverage")}>`;
    svg += `<rect x="${x0}" y="${baseline - 24}" width="${x1 - x0}" height="18" fill="#D6D8DC" rx="1"/>`;
    svg += `<text class="band__label" x="${(x0 + x1) / 2}" y="${baseline - 11}" text-anchor="middle">${filter.name}</text>`;
    svg += `</g>`;
  }

  // SPAM bands sit above, all the same height. Only the horizontal extent
  // carries information, so nothing else is scaled.
  for (const filter of SPAM_FILTERS) {
    const x0 = xFor(filter.blue);
    const x1 = xFor(filter.red);
    const centre = (x0 + x1) / 2;
    const y = baseline - 30 - barHeight;
    const color = bandColor(filter.pivot);

    const program = filter.shared ? "SPAM + MINERVA" : "SPAM";

    svg += `<g class="band" tabindex="0" ${dataAttrs(filter, program)}>`;
    svg += `<rect x="${x0}" y="${y}" width="${x1 - x0}" height="${barHeight}" fill="${color}" rx="1"`;
    // Bands both programs observe get the fill and the dashed outline.
    if (filter.shared) svg += ` stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="4 3"`;
    svg += `/>`;
    svg += `<text class="band__label band__label--spam" x="${centre}" y="${y - 8}" text-anchor="start" `;
    svg += `transform="rotate(-90 ${centre} ${y - 8})">${filter.name}</text>`;
    svg += `</g>`;
  }

  // The two medium bands MINERVA adds that SPAM does not carry. Outlined
  // rather than filled, so it is clear they come from a different program.
  for (const filter of MINERVA_FILTERS) {
    const x0 = xFor(filter.blue);
    const x1 = xFor(filter.red);
    const centre = (x0 + x1) / 2;
    const y = baseline - 30 - barHeight;
    const color = bandColor(filter.pivot);

    svg += `<g class="band" tabindex="0" ${dataAttrs(filter, "MINERVA (GO 7814)")}>`;
    svg += `<rect x="${x0}" y="${y}" width="${x1 - x0}" height="${barHeight}" fill="none" `;
    svg += `stroke="${color}" stroke-width="2" stroke-dasharray="4 3" rx="1"/>`;
    svg += `<text class="band__label band__label--minerva" x="${centre}" y="${y - 8}" text-anchor="start" `;
    svg += `transform="rotate(-90 ${centre} ${y - 8})" style="fill:${color}">${filter.name}</text>`;
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
  attachTooltip(host);
}

/* Hover or focus a band to read its numbers. Uses one shared tooltip
   element rather than SVG <title>, which browsers show only after a
   delay and cannot style. */
function attachTooltip(host) {
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  host.appendChild(tip);

  function show(group) {
    const data = group.dataset;
    tip.innerHTML =
      `<span class="tip__name">${data.name}</span>` +
      `<span class="tip__program">${data.program}</span>` +
      `<dl class="tip__rows">` +
      `<dt>Bandwidth</dt><dd>${data.bw} \u00B5m</dd>` +
      `<dt>Pivot</dt><dd>${data.pivot} \u00B5m</dd>` +
      `</dl>`;
    tip.hidden = false;

    // Position above the bar, clamped so it never runs off either edge.
    const hostBox = host.getBoundingClientRect();
    const barBox = group.getBoundingClientRect();
    const centre = barBox.left + barBox.width / 2 - hostBox.left;
    const halfTip = tip.offsetWidth / 2;
    const clamped = Math.min(Math.max(centre, halfTip), hostBox.width - halfTip);

    tip.style.left = clamped + "px";

    // Prefer above the bar, but flip below when it would be clipped by the
    // top of the figure.
    const above = barBox.top - hostBox.top - tip.offsetHeight - 10;
    if (above >= 0) {
      tip.style.top = above + "px";
    } else {
      tip.style.top = (barBox.bottom - hostBox.top + 10) + "px";
    }
  }

  function hide() {
    tip.hidden = true;
  }

  for (const group of host.querySelectorAll(".band")) {
    group.addEventListener("mouseenter", () => show(group));
    group.addEventListener("focus", () => show(group));
    group.addEventListener("mouseleave", hide);
    group.addEventListener("blur", hide);
  }

  host.addEventListener("mouseleave", hide);
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
      // Everyone outside the PI and architect groups has no role label.
      if (member.role) html += `<p class="member__role">${escapeHtml(member.role)}</p>`;
      if (member.institution) html += `<p class="member__inst">${escapeHtml(member.institution)}</p>`;
      if (member.note) html += `<p class="member__note">${escapeHtml(member.note)}</p>`;
      if (member.website || member.orcid || member.email) {
        html += `<p class="member__links">`;
        if (member.website) html += `<a href="${escapeHtml(member.website)}">Website</a>`;
        if (member.orcid)   html += `<a href="https://orcid.org/${escapeHtml(member.orcid)}">ORCID</a>`;
        if (member.email)   html += `<a href="mailto:${escapeHtml(member.email)}">Email</a>`;
        html += `</p>`;
      }
      html += `</article>`;
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
