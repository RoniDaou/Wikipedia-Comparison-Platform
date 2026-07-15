/* ═══════════════════════════════════════════════════════════════════════════
   cluster.js — ClusterNations frontend application.

   API endpoints used:
     GET    /api/cluster/matrices                    — list all matrices
     GET    /api/cluster/matrix/<id>                 — get full matrix
     DELETE /api/cluster/matrix/<id>                 — delete one matrix
     POST   /api/cluster/build-matrix               — build new matrix
     GET    /api/cluster/matrix-status              — build progress
     GET    /api/cluster/results[?algorithm=]       — list all results
     GET    /api/cluster/result/<id>                — get full result
     DELETE /api/cluster/result/<id>                — delete one result
     POST   /api/cluster/run                        — run algorithm
     GET    /api/cluster/neighbors/<country>        — similar countries
     GET    /api/cluster/top-pairs                  — global top pairs
     GET    /api/countries                          — country list
     GET    /api/statistics                         — DB stats
═══════════════════════════════════════════════════════════════════════════ */

const API = "https://wikipedia-comparison-platform.onrender.com";

/* ── App state ───────────────────────────────────────────────────────────── */
const State = {
  currentAlgo: "kmeans",
  lastResult: null,
  activeMatrixId: null, // _id of currently selected matrix
  pollTimer: null,
  fullMatrix: null, // full matrix doc (for scatter/heatmap)
};

/* ══════════════════════════════════════════════════════════════════════════
   BOOT
══════════════════════════════════════════════════════════════════════════ */

window.addEventListener("DOMContentLoaded", () => {
  loadCountrySelects();
  loadFeatureList();
  loadMatrixList(true); /* true = auto-select the most recent matrix */
  loadResultsList();
  loadStats();
  refreshBuildStatus();
});

/* ══════════════════════════════════════════════════════════════════════════
   TAB NAVIGATION
══════════════════════════════════════════════════════════════════════════ */

function openTab(name, btn) {
  /* hide hero/stats on all tabs except the first load */
  document
    .querySelectorAll(".tab-content")
    .forEach((el) => el.classList.remove("active"));
  document
    .querySelectorAll(".nav-btn")
    .forEach((el) => el.classList.remove("active"));

  const tab = document.getElementById(`tab-${name}`);
  if (tab) tab.classList.add("active");
  if (btn) btn.classList.add("active");

  /* hide hero after first nav click */
  const hero = document.getElementById("hero-section");
  const strip = document.getElementById("stats-strip");
  if (name !== "matrix") {
    hero.classList.remove("visible");
    strip.classList.remove("visible");
  }

  if (name === "cluster") {
    syncClusterMatrixCheck();
  }
  if (name === "results") {
    syncResultsTab();
    loadResultsList();
  }
  if (name === "explore") loadExploreTopPairs();
}

/* ══════════════════════════════════════════════════════════════════════════
   STATS
══════════════════════════════════════════════════════════════════════════ */

async function loadStats() {
  try {
    const res = await fetch(`${API}/api/statistics`);
    const data = await res.json();
    if (data.success) {
      setText("stat-countries", data.statistics.total_countries);
    }
  } catch (_) {}

  try {
    const res = await fetch(`${API}/api/cluster/matrix-status`);
    const data = await res.json();
    if (data.matrix) {
      setText("stat-matrix", `${data.matrix.count}×${data.matrix.count}`);
    }
  } catch (_) {}

  try {
    const res = await fetch(`${API}/api/cluster/results`);
    const data = await res.json();
    if (data.results && data.results.length > 0) {
      const counts = data.results
        .map((r) => r.n_clusters ?? r.k ?? "—")
        .join(" / ");
      setText("stat-clusters", counts);
    }
  } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════════════════
   COUNTRY PICKER
══════════════════════════════════════════════════════════════════════════ */

/* Region presets — country names must match exactly what's in your DB */
const PRESETS = {
  "middle-east": [
    "Lebanon",
    "Syria",
    "Jordan",
    "Palestine",
    "Iraq",
    "Iran",
    "Saudi Arabia",
    "Kuwait",
    "Bahrain",
    "Qatar",
    "United Arab Emirates",
    "Oman",
    "Yemen",
    "Turkey",
    "Cyprus",
  ],
  europe: [
    "France",
    "Germany",
    "United Kingdom",
    "Italy",
    "Spain",
    "Portugal",
    "Netherlands",
    "Belgium",
    "Switzerland",
    "Austria",
    "Sweden",
    "Norway",
    "Denmark",
    "Finland",
    "Poland",
    "Czech Republic",
    "Hungary",
    "Romania",
    "Greece",
    "Croatia",
    "Serbia",
    "Ukraine",
    "Albania",
    "Andorra",
    "Armenia",
    "Azerbaijan",
    "Belarus",
    "Bosnia and Herzegovina",
    "Bulgaria",
    "Estonia",
    "Georgia",
    "Iceland",
    "Latvia",
    "Lithuania",
    "Moldova",
    "Montenegro",
    "North Macedonia",
    "Slovakia",
    "Slovenia",
    "Russia",
    "San Marino",
    "Vatican City",
    "Malta",
    "Turkey",
    "Republic of Ireland",
    "Cyprus",
    "Luxembourg",
    "Liechtenstein",
    "Monaco",
  ],
  asia: [
    "China",
    "Japan",
    "South Korea",
    "India",
    "Pakistan",
    "Bangladesh",
    "Indonesia",
    "Vietnam",
    "Thailand",
    "Malaysia",
    "Singapore",
    "Philippines",
    "Myanmar",
    "Nepal",
    "Sri Lanka",
    "Afghanistan",
    "Kazakhstan",
    "Uzbekistan",
    "Mongolia",
    "Lebanon",
    "Syria",
    "Jordan",
    "Saudi Arabia",
    "Iraq",
    "Iran",
    "Kuwait",
    "Bahrain",
    "Qatar",
    "United Arab Emirates",
    "Oman",
    "Yemen",
  ],
  americas: [
    "United States",
    "Canada",
    "Mexico",
    "Brazil",
    "Argentina",
    "Colombia",
    "Chile",
    "Peru",
    "Venezuela",
    "Ecuador",
    "Bolivia",
    "Paraguay",
    "Uruguay",
    "Cuba",
    "Dominican Republic",
    "Haiti",
    "Jamaica",
    "Guatemala",
    "Honduras",
    "Panama",
    "Costa Rica",
    "El Salvador",
    "Nicaragua",
    "Puerto Rico",
    "Trinidad and Tobago",
    "Bahamas",
    "Barbados",
    "Belize",
    "Bermuda",
    "Guyana",
    "Suriname",
  ],
  africa: [
    "Egypt",
    "Nigeria",
    "South Africa",
    "Kenya",
    "Ethiopia",
    "Ghana",
    "Tanzania",
    "Morocco",
    "Algeria",
    "Tunisia",
    "Libya",
    "Sudan",
    "Uganda",
    "Cameroon",
    "Ivory Coast",
    "Senegal",
    "Angola",
    "Mozambique",
    "Zambia",
    "Zimbabwe",
    "Mali",
    "Niger",
    "Burkina Faso",
    "Madagascar",
    "Botswana",
    "Namibia",
    "Mauritius",
    "Rwanda",
    "Burundi",
    "Sierra Leone",
    "Liberia",
    "Somalia",
    "Eritrea",
    "Djibouti",
    "Gambia",
    "Guinea",
    "Guinea-Bissau",
    "Cape Verde",
    "Comoros",
    "São Tomé and Príncipe",
  ],
};

/* Approximate seconds per TED pair */
const SECS_PER_PAIR = 1.5;

let _allCountries = []; /* full list from DB */
let _selected = new Set();
let _allFeatures = []; /* available infobox fields from DB */
let _selectedFeatures = new Set();

async function loadCountrySelects() {
  try {
    const res = await fetch(`${API}/api/countries`);
    const data = await res.json();
    _allCountries = data.countries || [];
  } catch (_) {
    _allCountries = [];
  }

  _buildPickerList(_allCountries);
  _populateExploreSelect(_allCountries);
  updateEstimate();
}

function _buildPickerList(countries) {
  const list = document.getElementById("picker-list");
  if (!list) return;
  list.innerHTML = "";

  countries.forEach((c) => {
    const item = document.createElement("label");
    item.className = "picker-item" + (_selected.has(c) ? " checked" : "");
    item.dataset.name = c.toLowerCase();

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = c;
    cb.checked = _selected.has(c);
    cb.addEventListener("change", () => {
      if (cb.checked) {
        _selected.add(c);
        item.classList.add("checked");
      } else {
        _selected.delete(c);
        item.classList.remove("checked");
      }
      _updatePickerCount();
      updateEstimate();
      if (
        document.getElementById("matrix-mode-select")?.value === "feature_ted"
      ) {
        loadFeatureList();
      }
    });

    item.appendChild(cb);
    item.appendChild(document.createTextNode(c));
    list.appendChild(item);
  });

  _updatePickerCount();
}

function _updatePickerCount() {
  const el = document.getElementById("picker-count");
  if (el) el.textContent = `${_selected.size} selected`;
}

function filterPickerList() {
  const q = (
    document.getElementById("country-search")?.value || ""
  ).toLowerCase();
  const items = document.querySelectorAll(".picker-item");
  items.forEach((item) => {
    item.classList.toggle(
      "hidden",
      q.length > 0 && !item.dataset.name.includes(q),
    );
  });
}

function applyPreset(name) {
  if (name === "none") {
    _selected.clear();
  } else if (name === "all") {
    _allCountries.forEach((c) => _selected.add(c));
  } else {
    const preset = PRESETS[name] || [];
    preset.forEach((c) => {
      /* fuzzy match — tolerate minor name differences */
      const match = _allCountries.find(
        (db) => db.toLowerCase() === c.toLowerCase(),
      );
      if (match) _selected.add(match);
    });
  }
  /* rebuild so checkboxes reflect new state */
  _buildPickerList(_allCountries);
  updateEstimate();
  if (document.getElementById("matrix-mode-select")?.value === "feature_ted") {
    loadFeatureList();
  }
}

function updateEstimate() {
  const banner = document.getElementById("estimate-banner");
  const icon = document.getElementById("estimate-icon");
  const text = document.getElementById("estimate-text");
  if (!banner || !text) return;

  const n = _selected.size;

  if (n === 0) {
    banner.className = "estimate-banner";
    icon.textContent = "📊";
    text.textContent = "Select countries below to see time estimate.";
    return;
  }

  const pairs = (n * (n - 1)) / 2;
  const secs = Math.round(pairs * SECS_PER_PAIR);
  const display = secs < 60;

  if (n <= 30) {
    banner.className = "estimate-banner";
    icon.textContent = "✅";
  } else if (n <= 60) {
    banner.className = "estimate-banner warn";
    icon.textContent = "⚠️";
  } else {
    banner.className = "estimate-banner danger";
    icon.textContent = "🐢";
  }

  text.textContent = `${n} countries → ${pairs.toLocaleString()} pairs → estimated ${display}`;
}

function _populateExploreSelect(countries) {
  const sel = document.getElementById("explore-country-select");
  if (!sel) return;
  sel.innerHTML = '<option value="">-- Select Country --</option>';
  countries.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    sel.appendChild(opt);
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   FEATURE-FILTERED TED MATRIX OPTIONS
══════════════════════════════════════════════════════════════════════════ */

function getFeatureScopeCountries() {
  // Country selection remains the main clustering scope.
  // If no countries are selected, the matrix builder uses all countries,
  // so the feature selector also falls back to all countries.
  return _selected.size > 0 ? Array.from(_selected) : [];
}

async function loadFeatureList() {
  try {
    const params = new URLSearchParams();
    getFeatureScopeCountries().forEach((country) => {
      params.append("countries", country);
    });

    const url = params.toString()
      ? `${API}/api/cluster/features?${params.toString()}`
      : `${API}/api/cluster/features`;

    const res = await fetch(url);
    const data = await res.json();
    _allFeatures = data.features || [];

    // If the user changes the country selection, remove features that are
    // no longer present in the chosen countries.
    _selectedFeatures = new Set(
      Array.from(_selectedFeatures).filter((feature) =>
        _allFeatures.includes(feature),
      ),
    );
  } catch (e) {
    console.error("Failed to load infobox features:", e);
    _allFeatures = [];
  }
  renderFeatureList(_allFeatures);
}

function toggleMatrixMode() {
  const mode =
    document.getElementById("matrix-mode-select")?.value || "full_ted";
  const section = document.getElementById("feature-filter-section");
  const incrementalBtn = document.getElementById("extend-matrix-btn");

  if (section)
    section.style.display = mode === "feature_ted" ? "block" : "none";
  if (mode === "feature_ted") {
    loadFeatureList();
  }
  if (incrementalBtn) {
    incrementalBtn.disabled = mode === "feature_ted";
    incrementalBtn.title =
      mode === "feature_ted"
        ? "Incremental extension is available only for full TED matrices."
        : "Extend the selected full TED matrix with new countries.";
  }
}

function renderFeatureList(features) {
  const list = document.getElementById("feature-list");
  if (!list) return;

  list.innerHTML = "";
  if (!features.length) {
    list.innerHTML =
      '<p class="saved-empty" style="padding:12px">No fields found yet. Scrape countries first, then refresh.</p>';
    updateFeatureCount();
    return;
  }

  features.forEach((feature) => {
    const item = document.createElement("label");
    item.className =
      "picker-item" + (_selectedFeatures.has(feature) ? " checked" : "");
    item.dataset.name = feature.toLowerCase();

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = feature;
    cb.checked = _selectedFeatures.has(feature);
    cb.addEventListener("change", () => {
      if (cb.checked) {
        _selectedFeatures.add(feature);
        item.classList.add("checked");
      } else {
        _selectedFeatures.delete(feature);
        item.classList.remove("checked");
      }
      updateFeatureCount();
    });

    item.appendChild(cb);
    item.appendChild(document.createTextNode(feature));
    list.appendChild(item);
  });

  updateFeatureCount();
}

function filterFeatureList() {
  const q = (
    document.getElementById("feature-search")?.value || ""
  ).toLowerCase();
  const filtered = _allFeatures.filter((f) => f.toLowerCase().includes(q));
  renderFeatureList(filtered);
}

function updateFeatureCount() {
  const el = document.getElementById("feature-count");
  if (el) el.textContent = `${_selectedFeatures.size} selected`;
}

function selectAllVisibleFeatures() {
  document
    .querySelectorAll("#feature-list .picker-item:not(.hidden) input")
    .forEach((cb) => {
      cb.checked = true;
      _selectedFeatures.add(cb.value);
      cb.closest(".picker-item")?.classList.add("checked");
    });
  updateFeatureCount();
}

function clearSelectedFeatures() {
  _selectedFeatures.clear();
  document
    .querySelectorAll("#feature-list .picker-item input")
    .forEach((cb) => {
      cb.checked = false;
      cb.closest(".picker-item")?.classList.remove("checked");
    });
  updateFeatureCount();
}

/* ══════════════════════════════════════════════════════════════════════════
   SIMILARITY MATRIX — list, build, select, delete
══════════════════════════════════════════════════════════════════════════ */

/* ── List all saved matrices ── */
async function loadMatrixList(autoSelect = false) {
  try {
    const res = await fetch(`${API}/api/cluster/matrices`);
    const data = await res.json();
    const matrices = data.matrices || [];

    /* Auto-select most recent if nothing is selected yet */
    if (autoSelect && matrices.length > 0 && !State.activeMatrixId) {
      await selectMatrix(
        matrices[0]._id,
      ); /* newest is first (sorted by saved_at DESC) */
    }

    _renderMatrixList(matrices);
  } catch (_) {
    _renderMatrixList([]);
  }
}

function _renderMatrixList(matrices) {
  const container = document.getElementById("matrix-list-container");
  if (!container) return;

  if (matrices.length === 0) {
    container.innerHTML =
      '<p class="saved-empty">No similarity matrices saved yet. Build one below.</p>';
    return;
  }

  container.innerHTML = matrices
    .map((m) => {
      const isActive = m._id === State.activeMatrixId;
      const countries =
        (m.countries || []).slice(0, 6).join(", ") +
        (m.countries?.length > 6 ? ` … +${m.countries.length - 6} more` : "");
      const modeLabel =
        m.matrix_mode === "feature_ted"
          ? `Feature-filtered TED · ${(m.selected_features || []).length} feature${(m.selected_features || []).length === 1 ? "" : "s"}`
          : "Full TED";
      const featureTitle = (m.selected_features || []).join(", ");
      return `
      <div class="saved-card ${isActive ? "saved-card-active" : ""}" id="mcard-${m._id}">
        <div class="saved-card-main">
          <div class="saved-card-title">${m.name || "Unnamed matrix"}</div>
          <div class="saved-card-meta">
            <span class="saved-badge">${m.count} countries</span>
            <span class="saved-badge" title="${escapeHtml(featureTitle)}">${modeLabel}</span>
            <span class="saved-date">${fmtDate(m.saved_at)}</span>
          </div>
          <div class="saved-card-countries" title="${(m.countries || []).join(", ")}">
            ${countries}
          </div>
        </div>
        <div class="saved-card-actions">
          <button class="btn btn-sm ${isActive ? "btn-primary" : "btn-secondary"}"
                  onclick="selectMatrix('${m._id}')">
            ${isActive ? "✓ Selected" : "Select"}
          </button>
          <button class="btn btn-sm btn-outline-danger"
                  onclick="deleteMatrixById('${m._id}')">🗑</button>
        </div>
      </div>`;
    })
    .join("");
}

async function selectMatrix(matrixId) {
  State.activeMatrixId = matrixId;
  /* fetch the full matrix so top-pairs and scatter work */
  try {
    const res = await fetch(`${API}/api/cluster/matrix/${matrixId}`);
    const data = await res.json();
    if (data.success) {
      State.fullMatrix = data.matrix;
      const n = data.matrix.count;
      setText("stat-matrix", `${n}×${n}`);
      /* show top-pairs for this matrix */
      document.getElementById("top-pairs-section").style.display = "";
      loadTopPairs(matrixId);
    }
  } catch (_) {}
  loadMatrixList(); /* re-render to show active highlight */
  syncClusterMatrixCheck();
}

async function deleteMatrixById(matrixId) {
  if (!confirm("Delete this similarity matrix?")) return;
  await fetch(`${API}/api/cluster/matrix/${matrixId}`, { method: "DELETE" });
  if (State.activeMatrixId === matrixId) {
    State.activeMatrixId = null;
    State.fullMatrix = null;
    _scatterCache.coords = null;
  }
  loadMatrixList();
  syncClusterMatrixCheck();
}

/* ── Build a new matrix ── */
async function buildMatrix(force = false) {
  const countries = _selected.size > 0 ? Array.from(_selected) : null;
  const name = document.getElementById("matrix-name-input")?.value.trim() || "";
  const matrixMode =
    document.getElementById("matrix-mode-select")?.value || "full_ted";
  const selectedFeatures = Array.from(_selectedFeatures);

  if (matrixMode === "feature_ted" && selectedFeatures.length === 0) {
    alert(
      "Please select at least one feature for feature-filtered TED clustering.",
    );
    return;
  }

  if (!countries) {
    const n = _allCountries.length;
    const pairs = (n * (n - 1)) / 2;
    const hrs = ((pairs * SECS_PER_PAIR) / 3600).toFixed(1);
    if (
      !confirm(
        `No countries selected — builds for all ${n} countries ` +
          `(${pairs.toLocaleString()} pairs, ~${hrs} hours).\n\nContinue?`,
      )
    )
      return;
  }

  setStatusBar(
    "matrix-status-bar",
    "building",
    "🔄",
    matrixMode === "feature_ted"
      ? `Building feature-filtered TED matrix (${selectedFeatures.length} feature${selectedFeatures.length === 1 ? "" : "s"})…`
      : `Building full TED matrix${countries ? ` (${countries.length} countries)` : ""}…`,
  );
  showBuildProgress(0, 0, "");

  try {
    const res = await fetch(`${API}/api/cluster/build-matrix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        countries,
        name,
        matrix_mode: matrixMode,
        features: matrixMode === "feature_ted" ? selectedFeatures : [],
      }),
    });
    const data = await res.json();
    if (!data.success) {
      setStatusBar("matrix-status-bar", "error", "❌", data.error);
      return;
    }
    _startPoll();
  } catch (e) {
    setStatusBar("matrix-status-bar", "error", "❌", e.message);
  }
}

async function buildMatrixIncremental() {
  const matrixMode =
    document.getElementById("matrix-mode-select")?.value || "full_ted";
  if (matrixMode === "feature_ted") {
    alert(
      "Incremental extension is only supported for full TED matrices. Build a new feature-filtered TED matrix instead.",
    );
    return;
  }
  if (!State.activeMatrixId) {
    alert("Select a base matrix first (from the list above).");
    return;
  }
  const name = document.getElementById("matrix-name-input")?.value.trim() || "";
  setStatusBar(
    "matrix-status-bar",
    "building",
    "🔄",
    "Extending matrix with new countries…",
  );
  showBuildProgress(0, 0, "");
  try {
    const res = await fetch(`${API}/api/cluster/build-matrix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incremental_from: State.activeMatrixId, name }),
    });
    const data = await res.json();
    if (!data.success) {
      setStatusBar("matrix-status-bar", "error", "❌", data.error);
      return;
    }
    _startPoll();
  } catch (e) {
    setStatusBar("matrix-status-bar", "error", "❌", e.message);
  }
}

/* ── Build progress polling ── */
async function refreshBuildStatus() {
  try {
    const res = await fetch(`${API}/api/cluster/matrix-status`);
    const data = await res.json();
    _applyBuildState(data.build_state || {});
  } catch (_) {}
}

function _applyBuildState(state) {
  if (state.running) {
    const pct =
      state.total > 0 ? Math.round((state.done / state.total) * 100) : 0;
    setStatusBar(
      "matrix-status-bar",
      "building",
      "🔄",
      `Building… ${state.done}/${state.total} pairs (${pct}%)`,
    );
    showBuildProgress(state.done, state.total, state.last_pair || "");
    _startPoll();
    return;
  }
  hideBuildProgress();
  if (state.error) {
    setStatusBar(
      "matrix-status-bar",
      "error",
      "❌",
      `Build error: ${state.error}`,
    );
    return;
  }
  if (state.finished && state.matrix_id) {
    setStatusBar(
      "matrix-status-bar",
      "ready",
      "✅",
      "Matrix built and saved successfully.",
    );
    loadMatrixList();
    /* auto-select the newly built matrix */
    selectMatrix(state.matrix_id);
  } else {
    setStatusBar(
      "matrix-status-bar",
      "unknown",
      "⏳",
      "No active build. Select or build a matrix above.",
    );
  }
}

function _startPoll() {
  if (State.pollTimer) return;
  State.pollTimer = setInterval(async () => {
    const res = await fetch(`${API}/api/cluster/matrix-status`);
    const data = await res.json();
    _applyBuildState(data.build_state || {});
    if (!data.build_state.running) {
      clearInterval(State.pollTimer);
      State.pollTimer = null;
      loadStats();
      loadMatrixList();
    }
  }, 2000);
}

function showBuildProgress(done, total, pair) {
  const wrap = document.getElementById("build-progress");
  if (!wrap) return;
  wrap.style.display = "block";
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  setText("build-progress-text", `${done} / ${total} pairs (${pct}%)`);
  const el = document.getElementById("build-progress-pair");
  if (el) el.textContent = pair;
  const fill = document.getElementById("build-progress-fill");
  if (fill) fill.style.width = `${pct}%`;
}

function hideBuildProgress() {
  const wrap = document.getElementById("build-progress");
  if (wrap) wrap.style.display = "none";
}

function syncClusterMatrixCheck() {
  const bar = document.getElementById("cluster-matrix-check");
  if (!bar) return;
  if (State.activeMatrixId && State.fullMatrix) {
    const n = State.fullMatrix.count;
    const modeLabel =
      State.fullMatrix.matrix_mode === "feature_ted"
        ? `Feature-filtered TED (${(State.fullMatrix.selected_features || []).length} feature${(State.fullMatrix.selected_features || []).length === 1 ? "" : "s"})`
        : "Full TED";
    bar.className = "matrix-status-bar matrix-status-ready";
    bar.innerHTML = `<span class="status-icon">✅</span>
      <span class="status-text">Matrix selected — ${n} countries · ${modeLabel} · ${State.fullMatrix.name || ""}</span>`;
  } else {
    bar.className = "matrix-status-bar matrix-status-unknown";
    bar.innerHTML = `<span class="status-icon">⚠️</span>
      <span class="status-text">No matrix selected. Go to Similarity Matrix tab and select one.</span>
      <button class="btn btn-secondary btn-sm"
        onclick="openTab('matrix', document.querySelectorAll('.nav-btn')[0])">
        Go to Matrix →
      </button>`;
  }
}

/* ── Top pairs ── */
async function loadTopPairs(matrixId) {
  const limit = document.getElementById("top-pairs-limit")?.value || 10;
  const mid = matrixId || State.activeMatrixId || "";
  try {
    const res = await fetch(
      `${API}/api/cluster/top-pairs?top=${limit}&matrix_id=${mid}`,
    );
    const data = await res.json();
    if (data.success) renderPairsTable("top-pairs-container", data.pairs);
  } catch (_) {}
}

function renderPairsTable(containerId, pairs) {
  const rows = pairs
    .map(
      (p, i) => `
    <tr>
      <td style="font-weight:600;color:var(--blue)">${i + 1}</td>
      <td>${p.country1}</td>
      <td>${p.country2}</td>
      <td>
        <div class="sim-bar-wrap">
          <div class="sim-bar-track">
            <div class="sim-bar-fill" style="width:${Math.round(p.similarity * 100)}%"></div>
          </div>
          <span class="sim-val">${(p.similarity * 100).toFixed(1)}%</span>
        </div>
      </td>
    </tr>`,
    )
    .join("");

  document.getElementById(containerId).innerHTML = `
    <div class="pairs-table-wrap">
      <table class="pairs-table">
        <thead><tr><th>#</th><th>Country 1</th><th>Country 2</th><th>Similarity</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* ══════════════════════════════════════════════════════════════════════════
   CLUSTERING — Algorithm selection
══════════════════════════════════════════════════════════════════════════ */

function toggleAutoCut() {
  const auto = document.getElementById("agg-auto-cut")?.checked;
  const wrap = document.getElementById("agg-n-clusters-wrap");
  if (!wrap) return;
  wrap.style.opacity = auto ? "0.4" : "1";
  wrap.style.pointerEvents = auto ? "none" : "auto";
}

function switchAlgo(algo) {
  State.currentAlgo = algo;

  document
    .getElementById("tab-btn-kmeans")
    .classList.toggle("active", algo === "kmeans");

  document
    .getElementById("tab-btn-agglomerative")
    .classList.toggle("active", algo === "agglomerative");

  document.getElementById("params-kmeans").style.display =
    algo === "kmeans" ? "" : "none";

  document.getElementById("params-agglomerative").style.display =
    algo === "agglomerative" ? "" : "none";
}

/* ══════════════════════════════════════════════════════════════════════════
   CLUSTER RESULTS — list, select, delete
══════════════════════════════════════════════════════════════════════════ */

async function loadResultsList() {
  try {
    const res = await fetch(`${API}/api/cluster/results`);
    const data = await res.json();
    _renderResultsList(data.results || []);
  } catch (_) {
    _renderResultsList([]);
  }
}

function _renderResultsList(results) {
  /* The list now lives in the Results tab */
  const container = document.getElementById("results-list-container");
  if (!container) return;

  if (results.length === 0) {
    container.innerHTML =
      '<p class="saved-empty">No clustering results saved yet. Run an algorithm in the Run Clustering tab.</p>';
    return;
  }

  container.innerHTML = results
    .map((r) => {
      const algo =
        r.algorithm === "kmeans"
          ? "K-Medoids"
          : "Agglomerative Hierarchical Clustering";
      const param =
        r.algorithm === "kmeans"
          ? `k=${r.k}`
          : `clusters=${r.n_clusters ?? "—"}`;
      const sil =
        r.silhouette != null ? `Sil: ${Number(r.silhouette).toFixed(3)}` : "";
      return `
      <div class="saved-card" id="rcard-${r._id}">
        <div class="saved-card-main">
          <div class="saved-card-title">${r.name || algo}</div>
          <div class="saved-card-meta">
            <span class="saved-badge algo-pill-${r.algorithm}">${r.algorithm === "kmeans" ? "K-Medoids" : "Agglomerative Hierarchical Clustering"}</span>
            <span class="saved-badge">${param}</span>
            <span class="saved-badge">${r.n_countries} countries</span>
            ${sil ? `<span class="saved-badge">${sil}</span>` : ""}
            <span class="saved-date">${fmtDate(r.saved_at)}</span>
          </div>
        </div>
        <div class="saved-card-actions">
          <button class="btn btn-sm btn-secondary"
                  onclick="loadResultById('${r._id}')">Load</button>
          <button class="btn btn-sm btn-outline-danger"
                  onclick="deleteResultById('${r._id}')">🗑</button>
        </div>
      </div>`;
    })
    .join("");
}

async function loadResultById(resultId) {
  showLoading("Loading result…");
  try {
    const res = await fetch(`${API}/api/cluster/result/${resultId}`);
    const data = await res.json();
    if (!data.success) {
      alert(data.error);
      return;
    }
    State.lastResult = data.result;
    /* also load the associated matrix for scatter */
    const mid = data.result.matrix_id;
    if (mid) {
      try {
        const mres = await fetch(`${API}/api/cluster/matrix/${mid}`);
        const mdata = await mres.json();
        if (mdata.success) {
          State.fullMatrix = mdata.matrix;
          State.activeMatrixId = mid;
          _scatterCache.coords = null;
          _scatterCache.countries = null;
        }
      } catch (_) {}
    }
    /* switch to results tab */
    openTab("results", document.querySelectorAll(".nav-btn")[2]);
    renderResult(data.result);
  } catch (e) {
    alert(`Failed: ${e.message}`);
  } finally {
    hideLoading();
  }
}

async function deleteResultById(resultId) {
  if (!confirm("Delete this cluster result?")) return;
  await fetch(`${API}/api/cluster/result/${resultId}`, { method: "DELETE" });
  loadResultsList();
}

/* ══════════════════════════════════════════════════════════════════════════
   RUN CLUSTERING
══════════════════════════════════════════════════════════════════════════ */

async function runClustering() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Running…";

  if (!State.activeMatrixId) {
    alert("Please select a similarity matrix first (Similarity Matrix tab).");
    btn.disabled = false;
    btn.textContent = "▶ Run Clustering";
    return;
  }

  const algo = State.currentAlgo;
  const name = document.getElementById("result-name-input")?.value.trim() || "";
  const body = { algorithm: algo, matrix_id: State.activeMatrixId, name };

  if (algo === "kmeans") {
    body.k = parseInt(document.getElementById("km-k").value) || 3;
    body.max_iter =
      parseInt(document.getElementById("km-max-iter").value) || 100;
    body.n_init = parseInt(document.getElementById("km-n-init").value) || 10;
  } else if (algo === "agglomerative") {
    const autoCut = document.getElementById("agg-auto-cut")?.checked;
    body.auto_cut = !!autoCut;
    if (!autoCut) {
      body.n_clusters =
        parseInt(document.getElementById("agg-n-clusters").value) || 3;
    }
    body.linkage = document.getElementById("agg-linkage").value || "average";
  }

  try {
    const res = await fetch(`${API}/api/cluster/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!data.success) {
      alert(`Clustering failed: ${data.error}`);
      return;
    }

    State.lastResult = data.result;
    _scatterCache.coords = null; /* reset so new result coords are used */

    loadStats();
    loadResultsList();
    openTab("results", document.querySelectorAll(".nav-btn")[2]);
    renderResult(data.result);
  } catch (e) {
    alert(`Request failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Run Clustering";
  }
}
/* ══════════════════════════════════════════════════════════════════════════
   RESULTS TAB
══════════════════════════════════════════════════════════════════════════ */

function syncResultsTab() {
  if (State.lastResult) renderResult(State.lastResult);
}

function renderResult(result) {
  document.getElementById("results-placeholder").style.display = "none";
  document.getElementById("results-main").style.display = "";

  const algo = result.algorithm;

  /* Badge & title */
  const badge = document.getElementById("results-algo-badge");
  badge.textContent =
    algo === "kmeans" ? "K-Medoids" : "Agglomerative Hierarchical Clustering";
  badge.style.background = algo === "kmeans" ? "var(--blue)" : "#059669";

  document.getElementById("results-title").textContent =
    algo === "kmeans"
      ? `K-Medoids — k = ${result.k}`
      : `Agglomerative Hierarchical Clustering — ${result.n_clusters ?? "—"} clusters · ${result.linkage || "average"} linkage`;

  /* Meta */
  const matrixModeInfo =
    State.fullMatrix?.matrix_mode === "feature_ted"
      ? `Feature-filtered TED: ${(State.fullMatrix.selected_features || []).join(", ")}`
      : "Full TED matrix";

  document.getElementById("results-meta").innerHTML =
    `<span>${result.n_countries} countries</span>
     <span>·</span>
     <span title="${escapeHtml(matrixModeInfo)}">${matrixModeInfo.length > 60 ? matrixModeInfo.slice(0, 57) + "..." : matrixModeInfo}</span>
     <span>·</span>
     <span>${fmtDate(result.computed_at)}</span>`;

  /* Metrics */
  renderMetrics(result);

  /* Views */
  renderCards(result);
  renderTable(result);

  renderDendrogram(result);
  renderMergeHistory(result);

  /* Default view */
  switchView("cards");
}

/* ── Metrics ──────────────────────────────────────────────────────────────── */

function renderMetrics(result) {
  const tiles = [];
  if (result.algorithm === "kmeans") {
    tiles.push(["Clusters", result.k]);
    tiles.push(["Countries", result.n_countries]);
    tiles.push(["Total Cost", result.total_cost?.toFixed(4) ?? "—"]);
    tiles.push(["Cohesion", result.cohesion?.toFixed(4) ?? "—"]);
    tiles.push(["Silhouette", result.silhouette?.toFixed(4) ?? "—"]);
  } else {
    tiles.push(["Clusters", result.n_clusters ?? "—"]);
    tiles.push(["Countries", result.n_countries]);
    tiles.push(["Linkage", result.linkage || "average"]);
    tiles.push(["Cohesion", result.cohesion?.toFixed(4) ?? "—"]);
    tiles.push(["Silhouette", result.silhouette?.toFixed(4) ?? "—"]);
    tiles.push([
      "Runtime",
      result.runtime_ms != null
        ? `${Number(result.runtime_ms).toFixed(1)} ms`
        : "—",
    ]);
  }

  document.getElementById("metrics-strip").innerHTML = tiles
    .map(
      ([lbl, val]) => `
    <div class="metric-tile">
      <span class="metric-val">${val}</span>
      <span class="metric-lbl">${lbl}</span>
    </div>`,
    )
    .join("");
}

/* ── Colour palette ───────────────────────────────────────────────────────── */

/* -- Hierarchical clustering visualizations ------------------------------- */

function getAgglomerativeHistory(result) {
  return result?.dendrogram || result?.merge_history || [];
}

function showAgglomerativeOnlyMessage(container, viewName) {
  if (!container) return;
  container.innerHTML = `<p class="saved-empty">${viewName} is available only for Agglomerative Hierarchical Clustering results.</p>`;
}

// ── Draggable cut line on dendrogram ────────────────────────────────────────
// Lets the user drag the cut line up/down to interactively choose n_clusters.
// Recomputes cluster assignments live from merge_history without a server call.
function initDendrogramCutLine(uid, result) {
  const wrap = document.getElementById(uid + "_wrap");
  const svg = document.getElementById(uid + "_svg");
  const cutLineEl = document.getElementById(uid + "_cutline");
  const hitEl = document.getElementById(uid + "_cutline_hit");
  const cutLabelEl = document.getElementById(uid + "_cutlabel");
  const cutInfoEl = document.getElementById(uid + "_cutinfo");
  if (!wrap || !svg || !cutLineEl) return;

  const history = result.merge_history || result.dendrogram || [];
  if (!history.length) return;

  const vb = svg.getAttribute("viewBox").split(" ").map(Number);
  const svgH = vb[3];

  // Must mirror layout constants from buildDendrogramSvg exactly
  const margin = { top: 55, right: 70, bottom: 130, left: 80 };
  const baselineY = svgH - margin.bottom;
  const plotHeight = baselineY - margin.top;
  const maxDist = Math.max(
    ...history.map((m) => Number(m.distance) || 0),
    1e-9,
  );

  // yScale (same formula as buildDendrogramSvg):
  //   dist=0       → y = baselineY       (bottom, similarity=1.0)
  //   dist=maxDist → y = baselineY - plotHeight*0.95  (top, low similarity)
  function distanceToSvgY(dist) {
    return baselineY - ((Number(dist) || 0) / maxDist) * plotHeight * 0.95;
  }

  // Inverse: SVG y → distance
  function svgYToDistance(svgY) {
    return Math.max(
      0,
      Math.min(maxDist, ((baselineY - svgY) / (plotHeight * 0.95)) * maxDist),
    );
  }

  // How many clusters does cutting at this distance threshold produce?
  function distanceToClusters(threshold) {
    const mergesDone = history.filter(
      (m) => Number(m.distance) <= threshold,
    ).length;
    return Math.max(1, history.length + 1 - mergesDone);
  }

  // Convert clientY (page pixels) → SVG coordinate space, respecting zoom/pan
  function clientYToSvgY(clientY) {
    const wrapRect = wrap.getBoundingClientRect();
    const scale = parseFloat(svg.dataset.scale || "1") || 1;
    const ty = parseFloat(svg.dataset.ty || "0") || 0;
    return (clientY - wrapRect.top - ty) / scale;
  }

  // Initial cut position: midpoint between last kept merge and first discarded merge
  const cutStep = result.cut_step || 0;
  let initDist;
  if (cutStep > 0 && cutStep <= history.length) {
    const lastKept = Number(history[cutStep - 1]?.distance) || 0;
    const firstDropped = Number(history[cutStep]?.distance) || maxDist;
    initDist = (lastKept + firstDropped) / 2;
  } else {
    initDist = maxDist * 0.5;
  }

  let currentDist = Math.max(0, Math.min(maxDist, initDist));
  let dragging = false;

  function updateCutLine(dist) {
    currentDist = Math.max(0, Math.min(maxDist, dist));
    const svgY = distanceToSvgY(currentDist);
    const nClusters = distanceToClusters(currentDist);
    const sim = (1 - currentDist).toFixed(3);

    // Move visible line and transparent hit area
    cutLineEl.setAttribute("y1", svgY);
    cutLineEl.setAttribute("y2", svgY);
    if (hitEl) {
      hitEl.setAttribute("y1", svgY);
      hitEl.setAttribute("y2", svgY);
    }
    if (cutLabelEl) {
      cutLabelEl.setAttribute("y", svgY - 8);
      cutLabelEl.textContent = `cut: ${nClusters} cluster${nClusters !== 1 ? "s" : ""} (sim ≥ ${sim})`;
    }
    if (cutInfoEl) {
      cutInfoEl.textContent = `${nClusters} cluster${nClusters !== 1 ? "s" : ""} · similarity threshold: ${sim}`;
    }
  }

  // Attach drag to the HIT AREA (not cutLineEl which has pointer-events:none)
  const dragTarget = hitEl || cutLineEl;

  dragTarget.addEventListener("mousedown", function (e) {
    dragging = true;
    e.stopPropagation();
    e.preventDefault();
    document.body.style.cursor = "ns-resize";
  });

  window.addEventListener("mousemove", function (e) {
    if (!dragging) return;
    updateCutLine(svgYToDistance(clientYToSvgY(e.clientY)));
  });

  window.addEventListener("mouseup", function () {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = "";
    wrap.style.cursor = "grab";
  });

  dragTarget.addEventListener(
    "touchstart",
    function (e) {
      dragging = true;
      e.stopPropagation();
    },
    { passive: true },
  );
  window.addEventListener(
    "touchmove",
    function (e) {
      if (!dragging) return;
      updateCutLine(svgYToDistance(clientYToSvgY(e.touches[0].clientY)));
    },
    { passive: true },
  );
  window.addEventListener("touchend", function () {
    dragging = false;
  });

  // Set initial position
  updateCutLine(currentDist);

  // Apply Cut button
  const applyBtn = document.getElementById(uid + "_applycut");

  if (applyBtn) {
    applyBtn.addEventListener("click", async function () {
      const resultId = State.lastResult?._id;
      if (!resultId) {
        alert("No saved result to recut. Run the clustering first.");
        return;
      }

      const newCutStep = history.filter(
        (m) => Number(m.distance) <= currentDist,
      ).length;

      applyBtn.disabled = true;
      applyBtn.textContent = "⏳ Applying…";

      // Hide save banner while applying
      const banner = document.getElementById("recut-save-banner");
      if (banner) banner.style.display = "none";

      try {
        const res = await fetch(`${API}/api/cluster/recut`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ result_id: resultId, cut_step: newCutStep }),
        });
        const data = await res.json();
        if (!data.success) {
          alert("Recut failed: " + data.error);
          return;
        }

        State.lastResult = data.result;
        renderResult(data.result);

        // Show the permanent save banner (in cluster.html) with stored cut info
        showRecutSaveBanner(data.result, resultId, newCutStep);
      } catch (err) {
        alert("Recut error: " + err.message);
      } finally {
        applyBtn.disabled = false;
        applyBtn.textContent = "✓ Apply Cut";
      }
    });
  }
}

// ── Recut save banner (permanent element in cluster.html) ─────────────────
function showRecutSaveBanner(recutResult, originalResultId, cutStep) {
  const banner = document.getElementById("recut-save-banner");
  const saveBtn = document.getElementById("recut-save-btn");
  const dismissBtn = document.getElementById("recut-dismiss-btn");
  const nameInput = document.getElementById("recut-save-name");
  if (!banner) return;

  // Clear previous name
  if (nameInput) nameInput.value = "";

  banner.style.display = "flex";

  // Dismiss
  if (dismissBtn) {
    dismissBtn.onclick = () => {
      banner.style.display = "none";
    };
  }

  // Save
  if (saveBtn) {
    // Remove old listener by cloning
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);

    newSaveBtn.addEventListener("click", async function () {
      const saveName = nameInput ? nameInput.value.trim() : "";
      newSaveBtn.disabled = true;
      newSaveBtn.textContent = "⏳ Saving…";

      try {
        const res = await fetch(`${API}/api/cluster/recut`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            result_id: originalResultId,
            cut_step: cutStep,
            save: true,
            save_name: saveName,
          }),
        });
        const data = await res.json();
        if (!data.success) {
          alert("Save failed: " + data.error);
          return;
        }

        State.lastResult = data.result;
        banner.style.display = "none";
        if (typeof loadResultsList === "function") loadResultsList();
        alert(`✓ Saved as "${saveName || "recut result"}" in database.`);
      } catch (err) {
        alert("Save error: " + err.message);
      } finally {
        newSaveBtn.disabled = false;
        newSaveBtn.textContent = "💾 Save to Database";
      }
    });
  }
}

// ── Dendrogram zoom / pan — called after innerHTML is set ────────────────────
function initDendrogramZoom(uid) {
  const wrap = document.getElementById(uid + "_wrap");
  const svg = document.getElementById(uid + "_svg");
  const btnIn = document.getElementById(uid + "_zoomin");
  const btnOut = document.getElementById(uid + "_zoomout");
  const btnRst = document.getElementById(uid + "_reset");
  if (!wrap || !svg) return;

  let scale = 1,
    tx = 0,
    ty = 0;
  let dragging = false,
    startX = 0,
    startY = 0,
    startTx = 0,
    startTy = 0;

  function apply() {
    svg.style.transform =
      "translate(" + tx + "px," + ty + "px) scale(" + scale + ")";
  }

  function zoomBy(factor, cx, cy) {
    cx = cx !== undefined ? cx : wrap.clientWidth / 2;
    cy = cy !== undefined ? cy : wrap.clientHeight / 2;
    const ns = Math.min(10, Math.max(0.15, scale * factor));
    tx = cx - (cx - tx) * (ns / scale);
    ty = cy - (cy - ty) * (ns / scale);
    scale = ns;
    apply();
  }

  // Toolbar buttons
  if (btnIn)
    btnIn.addEventListener("click", function () {
      zoomBy(1.3);
    });
  if (btnOut)
    btnOut.addEventListener("click", function () {
      zoomBy(0.75);
    });
  if (btnRst)
    btnRst.addEventListener("click", function () {
      scale = 1;
      tx = 0;
      ty = 0;
      svg.style.transform = "";
    });

  // Scroll to zoom (centered on mouse cursor)
  wrap.addEventListener(
    "wheel",
    function (e) {
      e.preventDefault();
      const rect = wrap.getBoundingClientRect();
      zoomBy(
        e.deltaY < 0 ? 1.15 : 0.87,
        e.clientX - rect.left,
        e.clientY - rect.top,
      );
    },
    { passive: false },
  );

  // Mouse drag to pan
  wrap.addEventListener("mousedown", function (e) {
    dragging = true;
    wrap.style.cursor = "grabbing";
    startX = e.clientX;
    startY = e.clientY;
    startTx = tx;
    startTy = ty;
    e.preventDefault();
  });
  window.addEventListener("mousemove", function (e) {
    if (!dragging) return;
    tx = startTx + (e.clientX - startX);
    ty = startTy + (e.clientY - startY);
    apply();
  });
  window.addEventListener("mouseup", function () {
    if (dragging) {
      dragging = false;
      wrap.style.cursor = "grab";
    }
  });

  // Touch: single-finger pan, two-finger pinch zoom
  let lastTouchDist = null;
  wrap.addEventListener(
    "touchstart",
    function (e) {
      if (e.touches.length === 1) {
        dragging = true;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        startTx = tx;
        startTy = ty;
      } else if (e.touches.length === 2) {
        lastTouchDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY,
        );
      }
    },
    { passive: true },
  );
  wrap.addEventListener(
    "touchmove",
    function (e) {
      if (e.touches.length === 1 && dragging) {
        tx = startTx + (e.touches[0].clientX - startX);
        ty = startTy + (e.touches[0].clientY - startY);
        apply();
      } else if (e.touches.length === 2 && lastTouchDist != null) {
        const d = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY,
        );
        zoomBy(d / lastTouchDist);
        lastTouchDist = d;
      }
    },
    { passive: true },
  );
  wrap.addEventListener("touchend", function () {
    dragging = false;
    lastTouchDist = null;
  });
}

function renderDendrogram(result) {
  const body = document.getElementById("dendrogram-body");
  if (!body) return;

  const history = getAgglomerativeHistory(result);
  if (result.algorithm !== "agglomerative" || history.length === 0) {
    showAgglomerativeOnlyMessage(body, "Dendrogram");
    return;
  }

  const svgHtml = buildDendrogramSvg(result, history);

  // Extract the uid stamped as an HTML comment so we can wire up zoom/pan.
  const uidMatch = svgHtml.match(/<!-- uid:(dg_\d+) -->/);
  const uid = uidMatch ? uidMatch[1] : null;

  body.innerHTML = `
    <div class="dendrogram-panel dendrogram-graph-panel">
      <h4>Dendrogram graph</h4>
      <p class="dendro-note">
        Graph view of the hierarchical clustering process. Leaves are countries, internal nodes are merges,
        and lower merge height means higher similarity.
      </p>
      ${svgHtml}
    </div>`;

  // Wire up zoom/pan NOW that the DOM is present.
  if (uid) {
    initDendrogramZoom(uid);
    initDendrogramCutLine(uid, result);
  }
}

function renderMergeHistory(result) {
  const body = document.getElementById("history-body");
  if (!body) return;

  const history = getAgglomerativeHistory(result);
  if (result.algorithm !== "agglomerative" || history.length === 0) {
    showAgglomerativeOnlyMessage(body, "Merge history");
    return;
  }

  const maxDist = Math.max(
    ...history.map((m) => Number(m.distance) || 0),
    1e-9,
  );
  const cutStep =
    result.cut_step ||
    Math.max(0, (result.n_countries || 0) - (result.n_clusters || 0));

  const rows = history
    .map((m) => {
      const dist = Number(m.distance) || 0;
      const width = Math.max(3, Math.round((dist / maxDist) * 100));
      const members = (m.members || []).join(", ");
      const isCut = m.step === cutStep;
      return `
      <tr class="${isCut ? "dendro-cut-row" : ""}">
        <td class="dendro-step">${m.step}</td>
        <td>${m.left} + ${m.right}</td>
        <td>${m.size}</td>
        <td class="dendro-sim">
          <div class="dendro-bar-wrap">
            <div class="dendro-bar" style="width:${width}%"></div>
            <span>${dist.toFixed(4)}</span>
          </div>
        </td>
        <td>${m.similarity != null ? Number(m.similarity).toFixed(4) : "—"}</td>
        <td class="dendro-members" title="${escapeHtml(members)}">${escapeHtml(members)}</td>
      </tr>`;
    })
    .join("");

  body.innerHTML = `
    <div class="dendrogram-panel">
      <h4>Hierarchical merge history</h4>
      <p class="dendro-note">Highlighted row marks the last merge kept to produce ${result.n_clusters} clusters.</p>
      <div class="dendro-table-wrap">
        <table class="dendro-table">
          <thead>
            <tr><th>Step</th><th>Merged clusters</th><th>Size</th><th>Distance</th><th>Similarity</th><th>Members</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

function buildDendrogramSvg(result, history) {
  const countries = getDendrogramCountryOrder(result, history);
  const n = countries.length;
  if (!n)
    return '<p class="saved-empty">No countries available for dendrogram.</p>';

  // Declare uid HERE — before any template literal uses it below.
  const uid = `dg_${Date.now()}`;

  const width = Math.max(980, n * 140);
  const height = 540;
  const margin = { top: 55, right: 70, bottom: 130, left: 80 };
  const baselineY = height - margin.bottom;
  const plotHeight = baselineY - margin.top;
  const xStep = n > 1 ? (width - margin.left - margin.right) / (n - 1) : 0;

  // ── FIX 1: Use actual distances as Y; never distort with artificial gaps ──
  // The old code pushed merges up by minMergeGapPx which caused all branches
  // to pile at the top (near distance=1.0) when real distances were clustered
  // close together (e.g. all 0.5 from feature-TED). The Y axis must faithfully
  // reflect actual distances — use proportional Y only.
  const maxDist = Math.max(
    ...history.map((m) => Number(m.distance) || 0),
    1e-9,
  );

  // Pad the top slightly so labels don't clip
  const yScale = (distance) =>
    baselineY - ((Number(distance) || 0) / maxDist) * plotHeight * 0.95;

  history.forEach((merge) => {
    merge._displayY = yScale(Number(merge.distance) || 0);
  });

  const cutStep =
    result.cut_step ||
    Math.max(0, (result.n_countries || 0) - (result.n_clusters || 0));
  const cutMerge = history.find((m) => Number(m.step) === Number(cutStep));
  const nextMerge = history.find((m) => Number(m.step) === Number(cutStep + 1));

  const nodes = new Map();
  countries.forEach((country, index) => {
    nodes.set(index, {
      id: index,
      x: margin.left + index * xStep,
      y: baselineY,
      distance: 0,
      label: country,
      members: [country],
    });
  });

  const parts = [];

  // Y-axis grid ticks — use actual distance scale
  const yTicks = 5;
  for (let i = 0; i <= yTicks; i++) {
    const dist = (maxDist / yTicks) * i;
    const y = yScale(dist);
    parts.push(
      `<line x1="${margin.left - 12}" y1="${y}" x2="${width - margin.right + 12}" y2="${y}" class="dendro-grid"/>`,
    );
    parts.push(
      `<text x="${margin.left - 16}" y="${y + 4}" class="dendro-axis-label" text-anchor="end">${(1 - dist).toFixed(2)}</text>`,
    );
  }

  // Draw branches
  history.forEach((merge) => {
    const left = nodes.get(Number(merge.left));
    const right = nodes.get(Number(merge.right));
    if (!left || !right) return;

    const parentX = (left.x + right.x) / 2;
    const parentY = merge._displayY;
    const parentId = n + Number(merge.step) - 1;

    parts.push(
      `<line x1="${left.x}" y1="${left.y}" x2="${left.x}" y2="${parentY}" class="dendro-branch"/>`,
    );
    parts.push(
      `<line x1="${right.x}" y1="${right.y}" x2="${right.x}" y2="${parentY}" class="dendro-branch"/>`,
    );
    parts.push(
      `<line x1="${left.x}" y1="${parentY}" x2="${right.x}" y2="${parentY}" class="dendro-branch"/>`,
    );

    // Show distance label on first, last, and every other merge
    if (
      merge.step === 1 ||
      merge.step === history.length ||
      merge.step % 2 === 0
    ) {
      parts.push(
        `<text x="${parentX}" y="${parentY - 7}" class="dendro-dist-label" text-anchor="middle">${(1 - Number(merge.distance)).toFixed(3)}</text>`,
      );
    }

    nodes.set(parentId, {
      id: parentId,
      x: parentX,
      y: parentY,
      distance: Number(merge.distance) || 0,
      members: merge.members || [...left.members, ...right.members],
    });
  });

  // Cut line — draggable, initialised by initDendrogramCutLine() after render
  {
    const cutY = nextMerge
      ? ((cutMerge?._displayY ?? baselineY) + nextMerge._displayY) / 2
      : (cutMerge?._displayY ?? yScale(maxDist * 0.5));
    // Thicker transparent hit area makes the line easy to grab
    parts.push(
      `<line id="${uid}_cutline_hit"
            x1="${margin.left - 8}" y1="${cutY}"
            x2="${width - margin.right + 8}" y2="${cutY}"
            stroke="transparent" stroke-width="14"
            style="cursor:ns-resize;"/>`,
    );
    parts.push(
      `<line id="${uid}_cutline"
            x1="${margin.left - 8}" y1="${cutY}"
            x2="${width - margin.right + 8}" y2="${cutY}"
            class="dendro-cut-line" style="cursor:ns-resize;pointer-events:none;"/>`,
    );
    parts.push(
      `<text id="${uid}_cutlabel"
            x="${width - margin.right}" y="${cutY - 8}"
            class="dendro-cut-label" text-anchor="end">cut: ${result.n_clusters} clusters</text>`,
    );
  }

  // Leaf dots + rotated labels
  countries.forEach((country, index) => {
    const x = margin.left + index * xStep;
    const short = country.length > 14 ? `${country.slice(0, 12)}…` : country;
    parts.push(
      `<circle cx="${x}" cy="${baselineY}" r="4" class="dendro-leaf-dot"><title>${escapeHtml(country)}</title></circle>`,
    );
    parts.push(
      `<text x="${x + 5}" y="${baselineY + 16}" class="dendro-leaf-label" transform="rotate(45 ${x + 5} ${baselineY + 16})">${escapeHtml(short)}</text>`,
    );
  });

  // Axes
  parts.push(
    `<line x1="${margin.left - 12}" y1="${baselineY}" x2="${width - margin.right + 12}" y2="${baselineY}" class="dendro-axis"/>`,
  );
  parts.push(
    `<line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${baselineY}" class="dendro-axis"/>`,
  );
  parts.push(
    `<text x="${margin.left - 52}" y="${margin.top + plotHeight / 2}" class="dendro-axis-title" text-anchor="middle" transform="rotate(-90 ${margin.left - 52} ${margin.top + plotHeight / 2})">Similarity</text>`,
  );

  return (
    `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;padding:8px 12px;background:#f8f5ff;border:1px solid #c4b5fd;border-radius:6px;flex-wrap:wrap;">
      <span style="font-size:0.8rem;">🖱 <strong>Drag the cut line</strong> up/down to change the number of clusters</span>
      <span id="${uid}_cutinfo" style="font-size:0.82rem;font-weight:600;color:#5b21b6;"></span>
      <button id="${uid}_applycut" style="margin-left:auto;padding:5px 14px;background:#5b21b6;color:#fff;border:none;border-radius:6px;font-size:0.82rem;font-weight:600;cursor:pointer;">✓ Apply Cut</button>
    </div>

    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
      <span style="font-size:0.8rem;font-weight:600;color:var(--ink-soft);">Zoom</span>
      <button id="${uid}_zoomin"  style="padding:4px 10px;border:1.5px solid var(--border);border-radius:6px;background:var(--white);cursor:pointer;font-size:0.85rem;font-weight:700;">＋</button>
      <button id="${uid}_zoomout" style="padding:4px 10px;border:1.5px solid var(--border);border-radius:6px;background:var(--white);cursor:pointer;font-size:0.85rem;font-weight:700;">－</button>
      <button id="${uid}_reset"   style="padding:4px 10px;border:1.5px solid var(--border);border-radius:6px;background:var(--white);cursor:pointer;font-size:0.82rem;">Reset</button>
      <span style="font-size:0.76rem;color:var(--ink-soft);margin-left:4px;">Scroll to zoom · Drag to pan</span>
    </div>
    <div id="${uid}_wrap" class="dendro-svg-wrap">
      <svg id="${uid}_svg" class="dendro-svg" viewBox="0 0 ${width} ${height}"
           style="transform-origin:top left;"
           role="img" aria-label="Agglomerative hierarchical dendrogram">
        ${parts.join("")}
      </svg>
    </div>` +
    // NOTE: zoom/pan JS is wired up by initDendrogramZoom() called after innerHTML is set
    `<!-- uid:${uid} -->`
  );
}

function getDendrogramCountryOrder(result, history) {
  if (result.labels) {
    const labelKeys = Object.keys(result.labels);
    if (labelKeys.length) return labelKeys;
  }

  const leafIds = new Set();
  const internalIds = new Set();
  const n = result.n_countries || 0 || history.length + 1;
  history.forEach((m) => {
    internalIds.add(n + Number(m.step) - 1);
    [Number(m.left), Number(m.right)].forEach((id) => {
      if (Number.isFinite(id) && id < n) leafIds.add(id);
    });
  });

  const fromHistory = Array.from(leafIds)
    .sort((a, b) => a - b)
    .map((id) => {
      for (const m of history) {
        const members = m.members || [];
        if (Number(m.left) === id || Number(m.right) === id) {
          return members.find(Boolean) || `Item ${id + 1}`;
        }
      }
      return `Item ${id + 1}`;
    });

  return fromHistory.length ? fromHistory : [];
}

const PALETTE = [
  "#009edb",
  "#f7941d",
  "#16a34a",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#d97706",
  "#db2777",
  "#059669",
  "#65a30d",
  "#4f46e5",
  "#c026d3",
  "#0284c7",
  "#15803d",
  "#b45309",
];

function clusterColor(id) {
  if (id === "noise" || id < 0) return "#94a3b8";
  return PALETTE[id % PALETTE.length];
}

/* ── Cards ────────────────────────────────────────────────────────────────── */

function renderCards(result) {
  const container = document.getElementById("cards-container");
  container.innerHTML = "";

  Object.values(result.clusters).forEach((cl) => {
    const color = clusterColor(cl.id);
    //const repKey = result.algorithm === 'kmeans' ? cl.medoid : cl.representative;
    const repKey = cl.medoid || cl.representative;
    const repLabel =
      result.algorithm === "kmeans"
        ? `⭐ Medoid: ${repKey}`
        : `📍 Rep: ${repKey}`;

    const chips = cl.members
      .map((m) => {
        const isRep = m === repKey;
        return `<span class="member-chip ${isRep ? "is-rep" : ""}"
                    style="border-color:${isRep ? color : "var(--border)"}">${m}</span>`;
      })
      .join("");

    const card = document.createElement("div");
    card.className = "cluster-card";
    card.innerHTML = `
      <div class="cluster-card-head" style="border-left:4px solid ${color}">
        <div class="cluster-card-title-row">
          <span class="cluster-id-pill" style="background:${color}">Cluster ${cl.id}</span>
          <span class="cluster-size-lbl">${cl.size} countr${cl.size === 1 ? "y" : "ies"}</span>
        </div>
        <span class="rep-tag">${repLabel}</span>
      </div>
      <div class="cluster-card-body">${chips}</div>`;
    container.appendChild(card);
  });
}

/* ── Table ────────────────────────────────────────────────────────────────── */

function renderTable(result) {
  const repSet = new Set(
    Object.values(result.clusters).map((cl) => cl.medoid || cl.representative),
  );

  const rows = Object.entries(result.labels)
    .sort(([, a], [, b]) => {
      if (a === "noise") return 1;
      if (b === "noise") return -1;
      return (a ?? 0) - (b ?? 0) || 0;
    })
    .map(([country, clusterId], idx) => {
      const isRep = repSet.has(country);
      const color = clusterColor(clusterId);
      const clLabel = clusterId === "noise" ? "Noise" : `Cluster ${clusterId}`;
      const role =
        clusterId === "noise"
          ? '<span class="role-noise">Outlier</span>'
          : isRep
            ? '<span class="role-rep">⭐ Representative</span>'
            : "Member";
      return `<tr>
        <td style="color:var(--ink-soft);font-size:0.82rem">${idx + 1}</td>
        <td style="font-weight:500">${country}</td>
        <td><span class="cluster-badge" style="background:${color}">${clLabel}</span></td>
        <td>${role}</td>
      </tr>`;
    })
    .join("");

  document.getElementById("table-body").innerHTML = rows;
}

/* ── View switching ───────────────────────────────────────────────────────── */

function switchView(view) {
  ["cards", "table", "heatmap", "scatter", "dendrogram", "history"].forEach(
    (v) => {
      document
        .getElementById(`vbtn-${v}`)
        .classList.toggle("active", v === view);
      document.getElementById(`view-${v}`).style.display =
        v === view ? "" : "none";
    },
  );
  if (view === "heatmap" && State.lastResult) renderHeatmap();
  if (view === "scatter" && State.lastResult) renderScatter();
  if (view === "dendrogram" && State.lastResult)
    renderDendrogram(State.lastResult);
  if (view === "history" && State.lastResult)
    renderMergeHistory(State.lastResult);
}

/* ══════════════════════════════════════════════════════════════════════════
   t-SNE  (t-Distributed Stochastic Neighbor Embedding — pure JS)
   Projects an N×N distance matrix down to 2D coordinates.

   Unlike MDS which tries to preserve ALL distances globally (causing
   distant-cluster distortion), t-SNE focuses on preserving LOCAL
   neighborhoods — points that are close in the real distance matrix
   will reliably appear close on screen, giving well-separated clusters.

   Parameters:
     perplexity : controls effective neighborhood size (default 5–15 for small N)
     iterations : gradient descent steps (default 800)
     learningRate: step size (default 80)
     earlyExaggeration: amplifies cluster separation early on (default 4)
══════════════════════════════════════════════════════════════════════════ */

function _tsne(
  distMatrix,
  {
    perplexity = 8,
    iterations = 900,
    learningRate = 80,
    earlyExaggeration = 4,
    seed = 42,
  } = {},
) {
  const n = distMatrix.length;

  /* ── Seeded PRNG (Mulberry32) for reproducible layouts ── */
  let _s = seed >>> 0;
  function rand() {
    _s |= 0;
    _s = (_s + 0x6d2b79f5) | 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /* ── Step 1: compute pairwise affinities P (high-dimensional) ──
     For each point i, fit a Gaussian so that the perplexity of the
     conditional distribution P(j|i) matches the target perplexity.
     P_ij = (P(j|i) + P(i|j)) / (2n)  — symmetrised                */
  const P = Array.from({ length: n }, () => new Float64Array(n));

  for (let i = 0; i < n; i++) {
    /* Binary search for σᵢ that achieves target perplexity */
    let lo = 0,
      hi = 1e10,
      sigma = 1.0;
    const targetEntropy = Math.log(perplexity);

    for (let iter = 0; iter < 50; iter++) {
      /* Compute unnormalised Gaussian affinities for row i */
      let sumExp = 0;
      const expRow = new Float64Array(n);
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const d2 = distMatrix[i][j] * distMatrix[i][j];
        expRow[j] = Math.exp(-d2 / (2 * sigma * sigma));
        sumExp += expRow[j];
      }
      if (sumExp === 0) sumExp = 1e-10;

      /* Shannon entropy H = -Σ p log p */
      let H = 0;
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const p = expRow[j] / sumExp;
        if (p > 1e-10) H -= p * Math.log(p);
      }

      /* Adjust sigma via binary search */
      if (H < targetEntropy) {
        lo = sigma;
        sigma = hi < 1e9 ? (sigma + hi) / 2 : sigma * 2;
      } else {
        hi = sigma;
        sigma = (lo + sigma) / 2;
      }
    }

    /* Store normalised P(j|i) */
    let sumExp = 0;
    const expRow = new Float64Array(n);
    for (let j = 0; j < n; j++) {
      if (i === j) continue;
      const d2 = distMatrix[i][j] * distMatrix[i][j];
      expRow[j] = Math.exp(-d2 / (2 * sigma * sigma));
      sumExp += expRow[j];
    }
    if (sumExp === 0) sumExp = 1e-10;
    for (let j = 0; j < n; j++) P[i][j] = expRow[j] / sumExp;
  }

  /* Symmetrise: P_ij = (P(j|i) + P(i|j)) / (2n) */
  for (let i = 0; i < n; i++)
    for (let j = i + 1; j < n; j++) {
      const v = (P[i][j] + P[j][i]) / (2 * n);
      P[i][j] = Math.max(v, 1e-12);
      P[j][i] = Math.max(v, 1e-12);
    }

  /* ── Step 2: initialise 2D embedding with small random values ── */
  let Y = Array.from({ length: n }, () => [
    (rand() - 0.5) * 0.01,
    (rand() - 0.5) * 0.01,
  ]);
  let Yp = Y.map((p) => [...p]); // previous positions (momentum)
  const gains = Array.from({ length: n }, () => [1, 1]);

  /* ── Step 3: gradient descent ── */
  for (let iter = 0; iter < iterations; iter++) {
    const exagg = iter < 250 ? earlyExaggeration : 1; // early exaggeration phase

    /* Compute low-dimensional affinities Q (Student t-distribution) */
    const num = Array.from({ length: n }, () => new Float64Array(n));
    let sumQ = 0;
    for (let i = 0; i < n; i++)
      for (let j = i + 1; j < n; j++) {
        const dx = Y[i][0] - Y[j][0];
        const dy = Y[i][1] - Y[j][1];
        const v = 1 / (1 + dx * dx + dy * dy); // t-distribution kernel
        num[i][j] = v;
        num[j][i] = v;
        sumQ += 2 * v;
      }
    if (sumQ === 0) sumQ = 1e-10;

    /* Gradient: dC/dYᵢ = 4 Σⱼ (exagg·Pᵢⱼ − Qᵢⱼ) · numᵢⱼ · (Yᵢ − Yⱼ) */
    const grad = Array.from({ length: n }, () => [0, 0]);
    for (let i = 0; i < n; i++)
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const Q = num[i][j] / sumQ;
        const mul = 4 * (exagg * P[i][j] - Q) * num[i][j];
        grad[i][0] += mul * (Y[i][0] - Y[j][0]);
        grad[i][1] += mul * (Y[i][1] - Y[j][1]);
      }

    /* Adaptive learning rate (per-parameter gains) + momentum */
    const momentum = iter < 250 ? 0.5 : 0.8;
    const newY = Y.map((p) => [...p]);

    for (let i = 0; i < n; i++)
      for (let d = 0; d < 2; d++) {
        /* Increase gain if gradient and momentum agree in sign */
        const sameSign = grad[i][d] > 0 === Y[i][d] - Yp[i][d] > 0;
        gains[i][d] = Math.max(
          0.1,
          sameSign ? gains[i][d] * 0.8 : gains[i][d] + 0.2,
        );
        const step = learningRate * gains[i][d] * grad[i][d];
        newY[i][d] = Y[i][d] - step + momentum * (Y[i][d] - Yp[i][d]);
      }

    /* Centre embedding at origin each iteration */
    for (let d = 0; d < 2; d++) {
      const mean = newY.reduce((s, p) => s + p[d], 0) / n;
      for (let i = 0; i < n; i++) newY[i][d] -= mean;
    }

    Yp = Y;
    Y = newY;
  }

  return Y; // Array of [x, y] coordinates
}

/* ══════════════════════════════════════════════════════════════════════════
   SCATTER PLOT RENDERER
   - t-SNE 2D projection of TED distance matrix
   - Colored dots per cluster, representative highlighted with outer ring
   - Cross (+) on the true centroid (mean of member t-SNE coordinates)
   - Hover tooltip, PNG download
══════════════════════════════════════════════════════════════════════════ */

/* Cache so t-SNE isn't re-run on every toolbar tweak */
const _scatterCache = { coords: null, countries: null, distMatrix: null };

async function renderScatter() {
  const canvas = document.getElementById("scatter-canvas");
  const tooltip = document.getElementById("scatter-tooltip");
  const legend = document.getElementById("scatter-legend");
  const result = State.lastResult;
  if (!canvas || !result) return;

  /* ── 1. Use pre-computed t-SNE coords from the backend result ── */
  // The backend runs K-Medoids on TED distances (correct assignments),
  // then t-SNE with high early-exaggeration + post-hoc cluster spread
  // for maximum visual separation. We use those coords directly here —
  // no JS-side projection needed, and the cluster colours are consistent.
  if (!result.coords || Object.keys(result.coords).length === 0) {
    canvas.parentElement.innerHTML =
      '<p style="padding:20px;color:var(--ink-soft)">⚠️ No projection coordinates in result. ' +
      "Re-run clustering to regenerate.</p>";
    return;
  }

  // Build parallel arrays in the matrix country order
  const countriesRaw =
    State.fullMatrix?.countries || Object.keys(result.coords);
  const countries = countriesRaw.filter((c) => result.coords[c] !== undefined);
  const coords = countries.map((c) => result.coords[c]);
  const n = countries.length;

  /* ── 2. Canvas sizing ── */
  const W = Math.min(760, canvas.parentElement.clientWidth || 760);
  const H = Math.round(W * 0.75);
  const PAD = { top: 52, right: 48, bottom: 52, left: 52 };
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");

  /* ── 3. Scale coords — extra margin so hulls don't clip ── */
  const xs = coords.map((p) => p[0]);
  const ys = coords.map((p) => p[1]);
  let xMin = Math.min(...xs),
    xMax = Math.max(...xs);
  let yMin = Math.min(...ys),
    yMax = Math.max(...ys);
  const xPad = (xMax - xMin) * 0.22 || 0.1;
  const yPad = (yMax - yMin) * 0.22 || 0.1;
  xMin -= xPad;
  xMax += xPad;
  yMin -= yPad;
  yMax += yPad;

  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  function toCanvas(px, py) {
    return [
      PAD.left + ((px - xMin) / xRange) * plotW,
      PAD.top + (1 - (py - yMin) / yRange) * plotH,
    ];
  }

  /* ── 4. Lookups ── */
  const labelMode = document.getElementById("scatter-labels")?.value || "hover";
  const dotR = parseInt(
    document.getElementById("scatter-dot-size")?.value || 9,
  );

  const clusterOf = {};
  Object.entries(result.labels).forEach(([c, cl]) => {
    clusterOf[c] = cl;
  });

  const medoidSet = new Set();
  Object.values(result.clusters).forEach((cl) => {
    medoidSet.add(cl.medoid || cl.representative);
  });

  /* Build canvas coords */
  const canvasCoords = [];

  countries.forEach((country, i) => {
    const cl = clusterOf[country];
    const colorId =
      cl === "noise" || cl === undefined
        ? -1
        : typeof cl === "number"
          ? cl
          : parseInt(cl);
    const color = clusterColor(colorId);
    const [cx, cy] = toCanvas(coords[i][0], coords[i][1]);
    canvasCoords.push({ country, cx, cy, color, cl, colorId });
  });

  /* ── 6. Background & grid ── */
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "#e2e8f0";
  ctx.lineWidth = 1;
  for (let gx = 0; gx <= 5; gx++) {
    const x = PAD.left + (gx / 5) * plotW;
    ctx.beginPath();
    ctx.moveTo(x, PAD.top);
    ctx.lineTo(x, PAD.top + plotH);
    ctx.stroke();
  }
  for (let gy = 0; gy <= 5; gy++) {
    const y = PAD.top + (gy / 5) * plotH;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(PAD.left + plotW, y);
    ctx.stroke();
  }
  ctx.strokeStyle = "#cbd5e1";
  ctx.strokeRect(PAD.left, PAD.top, plotW, plotH);

  /* Axis labels */
  ctx.font = "11px -apple-system,sans-serif";
  ctx.fillStyle = "#94a3b8";
  ctx.textAlign = "center";
  ctx.fillText("t-SNE Dimension 1", PAD.left + plotW / 2, H - 12);
  ctx.save();
  ctx.translate(14, PAD.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("t-SNE Dimension 2", 0, 0);
  ctx.restore();

  /* ── 7. Draw dots ── */
  canvasCoords.forEach(({ country, cx, cy, color, cl }) => {
    const isMedoid = medoidSet.has(country);
    const r = dotR;

    /* Outer ring for medoid */
    if (isMedoid) {
      ctx.beginPath();
      ctx.arc(cx, cy, r + 5, 0, Math.PI * 2);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.4;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.globalAlpha = isMedoid ? 1.0 : 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = isMedoid ? 2.5 : 1.5;
    ctx.stroke();

    /* Country label */
    const showLabel =
      labelMode === "always" || (labelMode === "reps" && isMedoid);
    if (showLabel) {
      const label = country.length > 13 ? country.slice(0, 12) + "…" : country;
      ctx.font = `${isMedoid ? "700" : "500"} ${isMedoid ? 11 : 10}px -apple-system,sans-serif`;
      ctx.fillStyle = "#1e293b";
      ctx.textAlign = "center";
      ctx.shadowColor = "#fff";
      ctx.shadowBlur = 3;
      ctx.fillText(label, cx, cy - r - 5);
      ctx.shadowBlur = 0;
    }
  });

  /* ── 9. Cross (+) on the TRUE CENTROID ──────────────────────────────────
     Always computed as the mean of the CANVAS positions of cluster members.
     This is guaranteed correct regardless of algorithm, because canvasCoords
     are the definitive positions already scaled and projected onto the canvas. */
  Object.entries(result.clusters).forEach(([clKey, cl]) => {
    const colorId = parseInt(clKey);
    const memberPts = canvasCoords.filter(
      (p) => String(p.cl) === String(clKey),
    );
    if (!memberPts.length) return;

    const cx = memberPts.reduce((s, p) => s + p.cx, 0) / memberPts.length;
    const cy = memberPts.reduce((s, p) => s + p.cy, 0) / memberPts.length;

    const ARM = 14,
      TH = 3;

    /* White halo */
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = TH + 3;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(cx - ARM, cy);
    ctx.lineTo(cx + ARM, cy);
    ctx.moveTo(cx, cy - ARM);
    ctx.lineTo(cx, cy + ARM);
    ctx.stroke();

    /* Dark cross */
    ctx.strokeStyle = "#1e293b";
    ctx.lineWidth = TH;
    ctx.beginPath();
    ctx.moveTo(cx - ARM, cy);
    ctx.lineTo(cx + ARM, cy);
    ctx.moveTo(cx, cy - ARM);
    ctx.lineTo(cx, cy + ARM);
    ctx.stroke();
  });

  /* ── 10. Tooltip ── */
  canvas._coords = canvasCoords;
  canvas._dotR = dotR;
  canvas._medoidSet = medoidSet;

  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    let hit = null;
    for (const pt of canvas._coords) {
      const dx = pt.cx - mx,
        dy = pt.cy - my;
      if (Math.sqrt(dx * dx + dy * dy) <= canvas._dotR + 6) {
        hit = pt;
        break;
      }
    }
    if (hit) {
      const isRep = canvas._medoidSet.has(hit.country);
      const clLabel = hit.cl === "noise" ? "Noise" : `Cluster ${hit.cl}`;
      const repLabel =
        result.algorithm === "kmeans"
          ? "★ Representative (closest to centroid)"
          : "★ Representative";
      tooltip.innerHTML =
        `<strong>${hit.country}</strong><br>${clLabel}` +
        (isRep ? `<br><span style="color:#fbbf24">${repLabel}</span>` : "");
      tooltip.style.display = "block";
      const wrapRect = canvas.parentElement.getBoundingClientRect();
      tooltip.style.left = `${e.clientX - wrapRect.left + 14}px`;
      tooltip.style.top = `${e.clientY - wrapRect.top - 12}px`;
    } else {
      tooltip.style.display = "none";
    }
  };
  canvas.onmouseleave = () => {
    tooltip.style.display = "none";
  };

  /* ── 11. Legend ── */
  const seenClusters = new Set();
  const legendItems = [];
  canvasCoords.forEach(({ cl, color }) => {
    const key = String(cl);
    if (!seenClusters.has(key)) {
      seenClusters.add(key);
      legendItems.push({ cl, color });
    }
  });
  legendItems.sort((a, b) => {
    if (a.cl === "noise") return 1;
    if (b.cl === "noise") return -1;
    return (parseInt(a.cl) || 0) - (parseInt(b.cl) || 0);
  });

  legend.innerHTML = `
    <div class="scatter-legend-item" style="margin-right:16px">
      <svg width="18" height="14" style="flex-shrink:0">
        <line x1="1" y1="7" x2="17" y2="7" stroke="#1e293b" stroke-width="2.5" stroke-linecap="round"/>
        <line x1="9" y1="1" x2="9" y2="13" stroke="#1e293b" stroke-width="2.5" stroke-linecap="round"/>
      </svg>
      <span>Centroid — mean position of cluster members</span>
    </div>
    <div class="scatter-legend-item" style="margin-right:16px">
      <svg width="18" height="14" style="flex-shrink:0">
        <circle cx="9" cy="7" r="5" fill="#009edb" stroke="#fff" stroke-width="2"/>
        <circle cx="9" cy="7" r="8" fill="none" stroke="#009edb" stroke-width="1.5" opacity="0.5"/>
      </svg>
      <span>Representative — country closest to centroid</span>
    </div>
    ${legendItems
      .map(({ cl, color }) => {
        const label = cl === "noise" ? "Noise / Outlier" : `Cluster ${cl}`;
        return `<div class="scatter-legend-item">
        <div class="scatter-legend-dot" style="background:${color}"></div>
        <span>${label}</span>
      </div>`;
      })
      .join("")}`;
}

function downloadScatter() {
  const canvas = document.getElementById("scatter-canvas");
  if (!canvas) return;
  const link = document.createElement("a");
  link.download = "cluster_scatter.png";
  link.href = canvas.toDataURL("image/png");
  link.click();
}

/* ── Heatmap ──────────────────────────────────────────────────────────────── */

async function renderHeatmap() {
  const wrap = document.getElementById("heatmap-wrap");
  const result = State.lastResult;
  if (!result) return;

  wrap.innerHTML =
    '<p style="color:var(--ink-soft);padding:16px">Loading heatmap…</p>';

  /* Always load the matrix that belongs to THIS result to get real scores. */
  const needsFetch =
    !State.fullMatrix ||
    !State.fullMatrix.matrix || // no actual cell data
    (result.matrix_id && State.fullMatrix._id !== result.matrix_id);

  if (needsFetch && result.matrix_id) {
    try {
      const res = await fetch(`${API}/api/cluster/matrix/${result.matrix_id}`);
      const data = await res.json();
      if (data.success) State.fullMatrix = data.matrix;
    } catch (_) {}
  }

  const matrixCountries = State.fullMatrix?.countries;
  if (!matrixCountries || !State.fullMatrix?.matrix) {
    wrap.innerHTML =
      '<p style="color:var(--ink-soft);padding:16px">No similarity matrix available. Make sure the matrix is still saved.</p>';
    return;
  }

  const limitVal = document.getElementById("heatmap-limit")?.value || "20";
  const sortBy = document.getElementById("heatmap-sort")?.value || "cluster";

  let countries = [...matrixCountries];

  if (sortBy === "cluster" && result.labels) {
    countries.sort((a, b) => {
      const la =
        result.labels[a] === "noise" ? 9999 : (result.labels[a] ?? 9999);
      const lb =
        result.labels[b] === "noise" ? 9999 : (result.labels[b] ?? 9999);
      return la - lb || a.localeCompare(b);
    });
  } else {
    countries.sort();
  }

  if (limitVal !== "0") countries = countries.slice(0, parseInt(limitVal));

  const n = countries.length;
  const CELL = Math.max(10, Math.min(28, Math.floor(520 / n)));
  const PAD = 90; /* left/top padding for labels */

  const canvas = document.createElement("canvas");
  canvas.width = PAD + n * CELL;
  canvas.height = PAD + n * CELL;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  /* Draw cells — use real similarity scores from the matrix */
  // Build index: country name → position in the full matrix
  const matrixIndex = new Map();
  State.fullMatrix.countries.forEach((c, i) => matrixIndex.set(c, i));

  for (let row = 0; row < n; row++) {
    for (let col = 0; col < n; col++) {
      let sim;
      if (row === col) {
        sim = 1.0;
      } else {
        const ri = matrixIndex.get(countries[row]);
        const ci = matrixIndex.get(countries[col]);
        sim =
          ri !== undefined && ci !== undefined
            ? (State.fullMatrix.matrix[ri][ci] ?? 0)
            : 0;
      }
      ctx.fillStyle = simToColor(sim);
      ctx.fillRect(PAD + col * CELL, PAD + row * CELL, CELL - 1, CELL - 1);
    }
  }

  /* Cluster boundary lines */
  if (sortBy === "cluster" && result.labels) {
    let prevCluster = result.labels[countries[0]];
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    for (let i = 1; i < n; i++) {
      const c = result.labels[countries[i]];
      if (c !== prevCluster) {
        ctx.beginPath();
        ctx.moveTo(PAD + i * CELL, PAD);
        ctx.lineTo(PAD + i * CELL, PAD + n * CELL);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(PAD, PAD + i * CELL);
        ctx.lineTo(PAD + n * CELL, PAD + i * CELL);
        ctx.stroke();
        prevCluster = c;
      }
    }
  }

  /* Row / column labels */
  const fontSize = Math.max(8, Math.min(11, CELL - 2));
  ctx.font = `${fontSize}px -apple-system,sans-serif`;
  ctx.fillStyle = "#3d4f5e";

  for (let i = 0; i < n; i++) {
    const label =
      countries[i].length > 14 ? countries[i].slice(0, 13) + "…" : countries[i];

    /* Row label (right-aligned) */
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillText(label, PAD - 4, PAD + i * CELL + CELL / 2);

    /* Column label (rotated) */
    ctx.save();
    ctx.translate(PAD + i * CELL + CELL / 2, PAD - 4);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(label, 0, 0);
    ctx.restore();
  }

  wrap.innerHTML = "";
  wrap.appendChild(canvas);
}

function simToColor(sim) {
  /* Low (red) → mid (orange) → high (green)  matching the sim bar */
  const r = sim < 0.5 ? 220 : Math.round(220 - (sim - 0.5) * 2 * 190);
  const g =
    sim < 0.5
      ? Math.round(sim * 2 * 167)
      : Math.round(167 + (sim - 0.5) * 2 * (40 - 167));
  const b =
    sim < 0.5
      ? Math.round(sim * 2 * 69)
      : Math.round(69 * (1 - (sim - 0.5) * 2));
  return `rgb(${r},${g},${b})`;
}

/* ══════════════════════════════════════════════════════════════════════════
   EXPLORE TAB
══════════════════════════════════════════════════════════════════════════ */

async function lookupNeighbours() {
  const country = document.getElementById("explore-country-select").value;
  const topN = parseInt(document.getElementById("explore-top-n").value) || 5;

  if (!country) {
    alert("Please select a country.");
    return;
  }

  showLoading(`Finding neighbours for ${country}…`);
  try {
    const res = await fetch(
      `${API}/api/cluster/neighbors/${encodeURIComponent(country)}?top=${topN}`,
    );
    const data = await res.json();
    hideLoading();

    if (!data.success) {
      alert(data.error);
      return;
    }

    const rows = data.neighbors
      .map(
        (n, i) => `
      <tr>
        <td style="font-weight:600;color:var(--blue)">${i + 1}</td>
        <td style="font-weight:500">${n.country}</td>
        <td>
          <div class="sim-bar-wrap">
            <div class="sim-bar-track">
              <div class="sim-bar-fill" style="width:${Math.round(n.similarity * 100)}%"></div>
            </div>
            <span class="sim-val">${(n.similarity * 100).toFixed(1)}%</span>
          </div>
        </td>
      </tr>`,
      )
      .join("");

    document.getElementById("neighbours-result").style.display = "";
    document.getElementById("neighbours-container").innerHTML = `
      <div class="pairs-table-wrap">
        <table class="pairs-table">
          <thead><tr><th>#</th><th>Country</th><th>Similarity to ${country}</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch (e) {
    hideLoading();
    alert(`Request failed: ${e.message}`);
  }
}

async function loadExploreTopPairs() {
  const section = document.getElementById("top-pairs-explore-section");
  if (!State.matrixMeta) {
    section.style.display = "none";
    return;
  }

  try {
    const res = await fetch(`${API}/api/cluster/top-pairs?top=10`);
    const data = await res.json();
    if (data.success) {
      section.style.display = "";
      renderPairsTable("top-pairs-explore-container", data.pairs);
    }
  } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════════════════════════════════ */

function setStatusBar(id, state, icon, text) {
  const bar = document.getElementById(id);
  if (!bar) return;
  bar.className = `matrix-status-bar matrix-status-${state}`;
  const icon_el = bar.querySelector(".status-icon");
  const text_el = bar.querySelector(".status-text");
  if (icon_el) icon_el.textContent = icon;
  if (text_el) text_el.textContent = text;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (_) {
    return iso;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showLoading(msg = "Loading…") {
  const el = document.getElementById("global-loading");
  document.getElementById("loading-msg").textContent = msg;
  el.classList.add("visible");
}

function hideLoading() {
  document.getElementById("global-loading").classList.remove("visible");
}
