const API_BASE = "https://wikipedia-scraper-35tw.onrender.com/api";

// ─────────────────────────────────────────────
//  State
// ─────────────────────────────────────────────

let treeImageZoom = 1;

let scrapingState = {
  isActive: false,
  isPaused: false,
  isStopped: false,
  currentIndex: 0,
  totalCountries: 0,
  countries: [],
  results: [],
  forceRescrape: false,
};

let isPanelMinimized = false;
let confirmModalResolve = null;
let bulkModalResolve = null;
let browseState = { allCountries: [], currentPage: 1, itemsPerPage: 10 };

// Store trees for image modal buttons
const treeImageStore = {};
let currentComparisonPatchState = null;
let currentPatchedJsonDoc = null;

// ─────────────────────────────────────────────
//  Init
// ─────────────────────────────────────────────

window.onload = function () {
  const hero = document.getElementById("hero-section");
  const stats = document.getElementById("stats-strip");
  if (hero) hero.classList.add("visible");
  if (stats) stats.classList.add("visible");

  loadStatistics();
  loadCountriesForComparison();
  loadCountryList();
};

// ─────────────────────────────────────────────
//  Tabs
// ─────────────────────────────────────────────

function openTab(tabName, btnEl) {
  document
    .querySelectorAll(".tab-content")
    .forEach((t) => t.classList.remove("active"));

  document
    .querySelectorAll(".nav-btn")
    .forEach((b) => b.classList.remove("active"));

  document.getElementById(tabName).classList.add("active");

  if (btnEl) btnEl.classList.add("active");

  const hero = document.getElementById("hero-section");
  const stats = document.getElementById("stats-strip");

  if (tabName === "scrape") {
    hero && hero.classList.add("visible");
    stats && stats.classList.add("visible");
  } else {
    hero && hero.classList.remove("visible");
    stats && stats.classList.remove("visible");
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ─────────────────────────────────────────────
//  Loading
// ─────────────────────────────────────────────

function showLoading() {
  document.getElementById("loading").style.display = "flex";
}

function hideLoading() {
  document.getElementById("loading").style.display = "none";
}

// ─────────────────────────────────────────────
//  Modals
// ─────────────────────────────────────────────

function showConfirmModal(countryName) {
  return new Promise((resolve) => {
    confirmModalResolve = resolve;
    const modal = document.getElementById("confirm-modal");
    document.getElementById("confirm-message").innerHTML = `
      <strong>"${countryName}"</strong> already exists in the database.<br><br>
      Do you want to <strong>re-scrape</strong> and update?<br><br>
      <em>Click "OK - Update Data" to refresh, or "Cancel" to keep existing data.</em>`;
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
  });
}

function closeConfirmModal(confirmed) {
  document.getElementById("confirm-modal").style.display = "none";
  document.body.style.overflow = "auto";
  if (confirmModalResolve) {
    confirmModalResolve(confirmed);
    confirmModalResolve = null;
  }
}

function showBulkScrapeModal() {
  return new Promise((resolve) => {
    bulkModalResolve = resolve;
    document.getElementById("bulk-scrape-modal").style.display = "flex";
    document.body.style.overflow = "hidden";
  });
}

function closeBulkModal(option) {
  document.getElementById("bulk-scrape-modal").style.display = "none";
  document.body.style.overflow = "auto";
  if (bulkModalResolve) {
    bulkModalResolve(option);
    bulkModalResolve = null;
  }
}

let currentTreeImageUrl = null;

function openTreeImageModal(treeKey, title = "Tree Preview") {
  try {
    const tree = treeImageStore[treeKey];
    if (!tree) {
      alert("Tree data not found.");
      return;
    }

    const svgMarkup = generateTreeSvgMarkup(tree, { maxDepth: 6 });

    if (currentTreeImageUrl) {
      URL.revokeObjectURL(currentTreeImageUrl);
      currentTreeImageUrl = null;
    }

    const blob = new Blob([svgMarkup], {
      type: "image/svg+xml;charset=utf-8",
    });

    currentTreeImageUrl = URL.createObjectURL(blob);

    const img = document.getElementById("tree-image-view");
    document.getElementById("tree-image-title").textContent = title;

    img.onload = null;
    img.onerror = null;

    img.onload = () => {
      resetTreeImageZoom();
    };

    img.onerror = null;

    img.src = currentTreeImageUrl;

    document.getElementById("tree-image-modal").style.display = "flex";
    document.body.style.overflow = "hidden";
  } catch (e) {
    console.error(e);
    alert("Failed to load tree image: " + e.message);
  }
}

function closeTreeImageModal() {
  const modal = document.getElementById("tree-image-modal");
  const img = document.getElementById("tree-image-view");

  if (modal) modal.style.display = "none";

  if (img) {
    img.onload = null;
    img.onerror = null;
    img.removeAttribute("src");
  }

  if (currentTreeImageUrl) {
    URL.revokeObjectURL(currentTreeImageUrl);
    currentTreeImageUrl = null;
  }

  treeImageZoom = 1;
  document.body.style.overflow = "auto";
}

function zoomTreeImage(factor) {
  const img = document.getElementById("tree-image-view");
  if (!img) return;

  treeImageZoom *= factor;
  treeImageZoom = Math.max(0.2, Math.min(treeImageZoom, 5));
  img.style.transform = `scale(${treeImageZoom})`;
  img.style.transformOrigin = "top left";
}

function resetTreeImageZoom() {
  const img = document.getElementById("tree-image-view");
  if (!img) return;

  treeImageZoom = 1;
  img.style.transform = "scale(1)";
  img.style.transformOrigin = "top left";
}

function registerTreeImage(tree) {
  const key = `tree_${Math.random().toString(36).slice(2, 10)}`;
  treeImageStore[key] = tree;
  return key;
}

// ─────────────────────────────────────────────
//  Scraping Panel
// ─────────────────────────────────────────────

function openScrapingPanel() {
  document.getElementById("scraping-panel").classList.remove("hidden");
  isPanelMinimized = false;
  updatePanelToggleButton();
  document.body.classList.add("panel-open");
}

function closeScrapingPanel() {
  document.getElementById("scraping-panel").classList.add("hidden");
  document.body.classList.remove("panel-open");
}

function togglePanelMinimize() {
  const panel = document.getElementById("scraping-panel");
  isPanelMinimized = !isPanelMinimized;
  panel.classList.toggle("minimized", isPanelMinimized);
  document.body.classList.toggle("panel-open", !isPanelMinimized);
  updatePanelToggleButton();
}

function updatePanelToggleButton() {
  const btn = document.getElementById("panel-toggle-btn");
  btn.innerHTML = isPanelMinimized ? "▶" : "◀";
  btn.title = isPanelMinimized ? "Expand panel" : "Minimize panel";
}

function updateProgress(current, total) {
  document.getElementById("progress-text").textContent = `${current}/${total}`;
  document.getElementById("progress-fill").style.width =
    total > 0 ? `${(current / total) * 100}%` : "0%";
}

function formatCountryName(name) {
  return name.replace(/_/g, " ");
}

function addCountryToPanel(country, status) {
  const list = document.getElementById("country-progress-list");
  let item = document.querySelector(`[data-country="${country}"]`);

  if (!item) {
    item = document.createElement("div");
    item.className = "country-item";
    item.setAttribute("data-country", country);
    list.insertBefore(item, list.firstChild);
  }

  item.className = "country-item " + status;

  const icons = {
    success: "✅",
    error: "❌",
    scraping: "⏳",
    skipped: "⏭️",
    updated: "♻️",
  };

  item.innerHTML = `<span class="icon">${icons[status] || ""}</span>
                    <span class="country-name">${formatCountryName(country)}</span>`;

  list.scrollTop = 0;
}

function togglePauseResume() {
  const btn = document.getElementById("pause-resume-btn");
  scrapingState.isPaused = !scrapingState.isPaused;

  if (scrapingState.isPaused) {
    btn.innerHTML = "▶️ Resume";
    btn.classList.replace("btn-secondary", "btn-warning");
  } else {
    btn.innerHTML = "⏸️ Pause";
    btn.classList.replace("btn-warning", "btn-secondary");
    continueScraping();
  }
}

function stopScraping() {
  scrapingState.isStopped = true;
  scrapingState.isActive = false;

  document.getElementById("scrape-result").style.display = "block";
  document.getElementById("scrape-result").innerHTML = `
    <div class="error-message">
      <h3>⏹️ Scraping Stopped</h3>
      <p>Scraped ${scrapingState.results.length} / ${scrapingState.totalCountries} countries.</p>
    </div>`;

  loadStatistics();
  loadCountriesForComparison();
  loadCountryList();

  setTimeout(() => {
    closeScrapingPanel();
    resetScrapingPanel();
  }, 2000);
}

function resetScrapingPanel() {
  scrapingState = {
    isActive: false,
    isPaused: false,
    isStopped: false,
    currentIndex: 0,
    totalCountries: 0,
    countries: [],
    results: [],
    forceRescrape: false,
  };

  document.getElementById("country-progress-list").innerHTML = "";
  updateProgress(0, 0);

  const btn = document.getElementById("pause-resume-btn");
  btn.innerHTML = "⏸️ Pause";
  btn.classList.remove("btn-warning");
  btn.classList.add("btn-secondary");
}

// ─────────────────────────────────────────────
//  Statistics
// ─────────────────────────────────────────────

async function loadStatistics() {
  try {
    const data = await (await fetch(`${API_BASE}/statistics`)).json();
    if (data.success) {
      document.getElementById("total-countries").textContent =
        data.statistics.total_countries || 0;
      document.getElementById("total-comparisons").textContent =
        data.statistics.total_comparisons || 0;

      if (data.statistics.last_scrape) {
        document.getElementById("last-updated").textContent = new Date(
          data.statistics.last_scrape,
        ).toLocaleDateString();
      }
    }
  } catch (e) {
    console.error(e);
  }
}

// ─────────────────────────────────────────────
//  Single country scrape
// ─────────────────────────────────────────────

async function checkCountryExists(name) {
  try {
    return (await (await fetch(`${API_BASE}/country/${name}`)).json()).success;
  } catch {
    return false;
  }
}

async function scrapeSingleCountry() {
  const countryName = document.getElementById("single-country").value.trim();

  if (!countryName) {
    alert("Please enter a country name");
    return;
  }

  const exists = await checkCountryExists(countryName);

  if (exists && !(await showConfirmModal(countryName))) {
    const r = document.getElementById("scrape-result");
    r.style.display = "block";
    r.innerHTML = `<div class="error-message"><h3>⏭️ Skipped</h3>
      <p>Existing data for "${countryName}" was kept.</p></div>`;
    return;
  }

  showLoading();

  try {
    const data = await (
      await fetch(`${API_BASE}/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          country_name: countryName,
          force_rescrape: exists,
        }),
      })
    ).json();

    hideLoading();

    const r = document.getElementById("scrape-result");
    r.style.display = "block";

    if (data.success) {
      r.innerHTML = `<div class="success-message">
        <h3>${exists ? "♻️" : "✅"} Success!</h3>
        <p>Successfully ${exists ? "updated" : "scraped"}: ${data.data.country_name}</p>
        <p><strong>Fields collected:</strong> ${Object.keys(data.data.fields).length}</p>
      </div>`;

      loadStatistics();
      loadCountriesForComparison();
      loadCountryList();
    } else {
      r.innerHTML = `<div class="error-message"><h3>❌ Error</h3><p>${data.error}</p></div>`;
    }
  } catch (e) {
    hideLoading();
    alert("Error: " + e.message);
  }
}

// ─────────────────────────────────────────────
//  Bulk scrape
// ─────────────────────────────────────────────

async function scrapeAllCountries() {
  const option = await showBulkScrapeModal();
  if (option === "cancel") return;

  resetScrapingPanel();
  showLoading();

  try {
    const data = await (await fetch(`${API_BASE}/un-countries`)).json();

    if (!data.success) {
      hideLoading();
      alert("Error fetching UN countries");
      return;
    }

    scrapingState.countries = data.countries;
    scrapingState.totalCountries = data.countries.length;
    scrapingState.isActive = true;
    scrapingState.forceRescrape = option === "rescrape-all";

    hideLoading();
    openScrapingPanel();
    updateProgress(0, scrapingState.totalCountries);
    continueScraping();
  } catch (e) {
    hideLoading();
    alert("Error: " + e.message);
  }
}

async function continueScraping() {
  let updated = 0;
  let skipped = 0;

  while (
    scrapingState.currentIndex < scrapingState.totalCountries &&
    scrapingState.isActive &&
    !scrapingState.isStopped
  ) {
    if (scrapingState.isPaused) {
      await sleep(500);
      continue;
    }

    const country = scrapingState.countries[scrapingState.currentIndex];
    const exists = await checkCountryExists(country);

    if (exists && !scrapingState.forceRescrape) {
      addCountryToPanel(country, "skipped");
      skipped++;
      scrapingState.currentIndex++;
      updateProgress(scrapingState.currentIndex, scrapingState.totalCountries);
      await sleep(500);
      continue;
    }

    addCountryToPanel(country, "scraping");

    try {
      const data = await (
        await fetch(`${API_BASE}/scrape`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            country_name: country,
            force_rescrape: scrapingState.forceRescrape,
          }),
        })
      ).json();

      if (data.success) {
        scrapingState.results.push(data.data);
        addCountryToPanel(
          country,
          exists && scrapingState.forceRescrape ? "updated" : "success",
        );

        if (exists && scrapingState.forceRescrape) updated++;
      } else {
        addCountryToPanel(country, "error");
      }
    } catch {
      addCountryToPanel(country, "error");
    }

    scrapingState.currentIndex++;
    updateProgress(scrapingState.currentIndex, scrapingState.totalCountries);
    await sleep(1000);
  }

  if (
    scrapingState.currentIndex >= scrapingState.totalCountries &&
    !scrapingState.isStopped
  ) {
    const r = document.getElementById("scrape-result");
    r.style.display = "block";
    r.innerHTML = `<div class="success-message"><h3>✅ Bulk Scrape Complete!</h3>
      <p>Scraped <strong>${scrapingState.results.length} countries</strong></p>
      ${skipped ? `<p>Skipped <strong>${skipped}</strong> (already in DB)</p>` : ""}
      ${updated ? `<p>Updated <strong>${updated}</strong> with fresh data</p>` : ""}
    </div>`;

    loadStatistics();
    loadCountriesForComparison();
    loadCountryList();

    setTimeout(() => {
      closeScrapingPanel();
      resetScrapingPanel();
    }, 3000);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ─────────────────────────────────────────────
//  Comparison dropdowns
// ─────────────────────────────────────────────

async function loadCountriesForComparison() {
  try {
    const [countriesRes, comparisonsRes, editedRes] = await Promise.all([
      fetch(`${API_BASE}/countries`),
      fetch(`${API_BASE}/comparisons`),
      fetch(`${API_BASE}/edited-countries`),
    ]);

    const countriesData = await countriesRes.json();
    const comparisonsData = await comparisonsRes.json();
    const editedData = await editedRes.json();

    if (countriesData.success) {
      const allOptions = [];

      // Add original countries
      if (countriesData.countries) {
        allOptions.push(
          ...countriesData.countries.map((c) => ({
            name: c,
            type: "country",
            label: `${formatCountryName(c)}`,
          })),
        );
      }

      // Add saved comparisons
      if (comparisonsData.success && comparisonsData.comparisons) {
        allOptions.push(
          ...comparisonsData.comparisons.map((c) => ({
            name: c,
            type: "comparison",
            label: `${formatCountryName(c)}`,
          })),
        );
      }

      // ✅ FIX: Handle edited countries (API returns array directly)
      if (Array.isArray(editedData) && editedData.length > 0) {
        // editedData is an array of country objects with country_name field
        allOptions.push(
          ...editedData.map((countryObj) => {
            const countryName = countryObj.country_name || "Unknown";
            return {
              name: countryName,
              type: "edited",
              label: `${formatCountryName(countryName)} [EDITED]`,
            };
          }),
        );
      }

      // Sort all options alphabetically by name
      allOptions.sort((a, b) => a.name.localeCompare(b.name));

      // Populate both dropdowns
      ["country1-select", "country2-select"].forEach((id) => {
        const sel = document.getElementById(id);
        sel.innerHTML = '<option value="">-- Select Country --</option>';

        allOptions.forEach((opt) => {
          sel.innerHTML += `<option value="${opt.name}">${opt.label}</option>`;
        });
      });

      // Enable keyboard letter jump AFTER populating
      enableDropdownLetterJump();
    }
  } catch (e) {
    console.error(e);
  }
}

function enableDropdownLetterJump() {
  ["country1-select", "country2-select"].forEach((id) => {
    const select = document.getElementById(id);
    if (select) {
      // Remove old listeners first
      select.replaceWith(select.cloneNode(true));
      const newSelect = document.getElementById(id);

      newSelect.addEventListener("keypress", function (e) {
        const key = e.key.toUpperCase();

        // Only handle letter keys (A-Z)
        if (/^[A-Z]$/.test(key)) {
          e.preventDefault();

          let startIndex = this.selectedIndex + 1;
          if (startIndex >= this.options.length) startIndex = 1;

          // Find first option starting with this letter
          for (let i = startIndex; i < this.options.length; i++) {
            const optionText = this.options[i].text.toUpperCase();
            if (optionText.startsWith(key) || optionText.includes(" " + key)) {
              this.selectedIndex = i;
              return;
            }
          }

          // If not found, search from beginning
          for (let i = 1; i < startIndex; i++) {
            const optionText = this.options[i].text.toUpperCase();
            if (optionText.startsWith(key) || optionText.includes(" " + key)) {
              this.selectedIndex = i;
              return;
            }
          }
        }
      });
    }
  });
}

// ─────────────────────────────────────────────
//  Comparison pipeline — button opens full tree image
// ─────────────────────────────────────────────

// ─────────────────────────────────────────────
//  COMPLETE COMPARISON PIPELINE (STEPS 1-6)
// ─────────────────────────────────────────────

// ─────────────────────────────────────────────
//  COMPLETE COMPARISON PIPELINE (STEPS 1-6)
// ─────────────────────────────────────────────

async function compareCountries() {
  // ───── VALIDATION ─────
  const country1 = document.getElementById("country1-select").value;
  const country2 = document.getElementById("country2-select").value;

  if (!country1 || !country2) {
    alert("Please select both countries");
    return;
  }

  if (country1 === country2) {
    alert("Please select different countries");
    return;
  }

  // ───── SETUP UI ─────
  const resultDiv = document.getElementById("comparison-result");
  resultDiv.style.display = "block";
  resultDiv.innerHTML = `
    <div class="pipeline-steps">
      <div class="step done">1. Data Collection</div>
      <div class="step active">2. Tree Construction</div>
      <div class="step active">3. TED</div>
      <div class="step active">4. Edit Script</div>
      <div class="step active">5. Patching</div>
      <div class="step active">6. Output</div>
    </div>
    <div class="cmp-loading-card">
      <h3>⏳ Running full comparison pipeline...</h3>
      <p>Loading trees, TED results, edit script, patched output, and JSON.</p>
    </div>
  `;

  showLoading();

  try {
    // ───── FETCH ALL DATA IN PARALLEL ─────
    const [compareRes, preprocessRes, country1FlatRes, country2FlatRes] =
      await Promise.all([
        fetch(`${API_BASE}/compare`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ country1, country2 }),
        }),
        fetch(`${API_BASE}/preprocess/compare`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ country1, country2 }),
        }),
        fetch(`${API_BASE}/country/${encodeURIComponent(country1)}`),
        fetch(`${API_BASE}/country/${encodeURIComponent(country2)}`),
      ]);

    const compareData = await compareRes.json();
    const preprocessData = await preprocessRes.json();
    const country1FlatData = await country1FlatRes.json();
    const country2FlatData = await country2FlatRes.json();

    hideLoading();

    console.log("[COMPARE] compareData:", compareData);
    console.log("[COMPARE] preprocessData:", preprocessData);
    console.log("[COMPARE] country1FlatData:", country1FlatData);
    console.log("[COMPARE] country2FlatData:", country2FlatData);

    // ───── ERROR CHECK ─────
    if (!compareData.success) {
      resultDiv.innerHTML = `<div class="error-message"><h3>❌ Error</h3><p>${compareData.error}</p></div>`;
      return;
    }

    // ───── EXTRACT COMPARISON DATA ─────
    const comp = compareData.comparison || {};
    const es = compareData.edit_script || {};
    const simPct = ((comp.similarity_score || 0) * 100).toFixed(2);
    const ted = Math.round((comp.ted_distance || 0) * 1000) / 1000;

    // ───── PROCESS OPERATIONS ─────
    const ops = es?.operations || [];

    const opCounts = ops.reduce(
      (acc, op) => {
        const type = String(op.op || op.type || "").toLowerCase();
        if (type === "match") acc.matches++;
        else if (type === "update") acc.updates++;
        else if (type === "insert") acc.inserts++;
        else if (type === "delete") acc.deletes++;
        return acc;
      },
      { matches: 0, updates: 0, inserts: 0, deletes: 0 },
    );

    const totalOperations =
      opCounts.updates + opCounts.inserts + opCounts.deletes;

    const nonMatch = ops.filter((o) => {
      const type = String(o.op || o.type || "").toLowerCase();
      return type !== "match";
    });

    // ───── BUILD TABLE ROWS ─────
    const opRows = nonMatch
      .map((op, i) => {
        const type = String(op.op || op.type || "").toLowerCase();
        return `
      <tr>
        <td>${i + 1}</td>
        <td><span class="op-badge op-${type}">${escapeHtml(
          type.toUpperCase() || "—",
        )}</span></td>
        <td><code>${escapeHtml(getOperationFieldLabel(op))}</code></td>
        <td class="val-cell">${escapeHtml(String(op.source?.value ?? "—"))}</td>
        <td class="val-cell">${escapeHtml(String(op.target?.value ?? "—"))}</td>
        <td>${escapeHtml(String(op.cost ?? 0))}</td>
      </tr>`;
      })
      .join("");

    const fullRows = ops
      .map((op, i) => {
        const type = String(op.op || op.type || "").toLowerCase();
        return `
      <tr>
        <td>${i + 1}</td>
        <td><span class="op-badge op-${type}">${escapeHtml(
          type.toUpperCase() || "—",
        )}</span></td>
        <td><code>${escapeHtml(getOperationFieldLabel(op))}</code></td>
        <td class="val-cell">${escapeHtml(String(op.source?.value ?? "—"))}</td>
        <td class="val-cell">${escapeHtml(String(op.target?.value ?? "—"))}</td>
        <td>${escapeHtml(String(op.cost ?? 0))}</td>
      </tr>`;
      })
      .join("");

    // ───── DETERMINE COLOR BY SIMILARITY ─────
    const simColor =
      comp.similarity_score >= 0.85
        ? "#22c55e"
        : comp.similarity_score >= 0.65
          ? "#eab308"
          : comp.similarity_score >= 0.4
            ? "#f97316"
            : "#ef4444";

    // ───── KEEP FLAT COUNTRY DOCS SEPARATE FROM BUILT TREE OBJECTS ─────
    const country1Doc =
      country1FlatData?.success && country1FlatData?.data
        ? country1FlatData.data
        : country1FlatData?.data
          ? country1FlatData.data
          : country1FlatData?.fields
            ? country1FlatData
            : null;

    const country2Doc =
      country2FlatData?.success && country2FlatData?.data
        ? country2FlatData.data
        : country2FlatData?.data
          ? country2FlatData.data
          : country2FlatData?.fields
            ? country2FlatData
            : null;

    currentComparisonPatchState = {
      country1,
      country2,
    };
    currentPatchedJsonDoc = null;

    let tree1Obj = null;
    let tree2Obj = null;

    if (preprocessData?.success) {
      tree1Obj = preprocessData.country1?.tree || null;
      tree2Obj = preprocessData.country2?.tree || null;
    }

    console.log("[COMPARE] country1Doc:", country1Doc);
    console.log("[COMPARE] country2Doc:", country2Doc);
    console.log("[COMPARE] tree1Obj:", tree1Obj);
    console.log("[COMPARE] tree2Obj:", tree2Obj);

    // ───── REGISTER KEYS ─────
    const tree1ViewKey = tree1Obj ? registerTreeImage(tree1Obj) : null;
    const tree2ViewKey = tree2Obj ? registerTreeImage(tree2Obj) : null;

    const tree1EditKey = country1Doc ? registerTreeImage(country1Doc) : null;
    const tree2EditKey = country2Doc ? registerTreeImage(country2Doc) : null;

    // ───── TREE BUTTONS ─────
    const tree1Button =
      tree1Obj && tree1Obj.label
        ? `
        <div class="tree-preview-card">
          <p>Full tree available as image preview or interactive editor.</p>
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button
              type="button"
              class="btn btn-primary"
              onclick="openTreeImageModal('${tree1ViewKey}', '${escapeJsString(
                formatCountryName(country1),
              )} Tree')">
              🌳 View Full Tree
            </button>
            ${
              country1Doc
                ? `
            <button
              type="button"
              class="btn btn-secondary"
              onclick="openTreeEditModal('${tree1EditKey}', '${escapeJsString(
                formatCountryName(country1),
              )} Tree', '${escapeJsString(country1)}')">
              ✏️ Edit Tree
            </button>`
                : ""
            }
          </div>
        </div>
      `
        : "<div class='tree-diagram-empty'>Tree unavailable</div>";

    const tree2Button =
      tree2Obj && tree2Obj.label
        ? `
        <div class="tree-preview-card">
          <p>Full tree available as image preview or interactive editor.</p>
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button
              type="button"
              class="btn btn-primary"
              onclick="openTreeImageModal('${tree2ViewKey}', '${escapeJsString(
                formatCountryName(country2),
              )} Tree')">
              🌳 View Full Tree
            </button>
            ${
              country2Doc
                ? `
            <button
              type="button"
              class="btn btn-secondary"
              onclick="openTreeEditModal('${tree2EditKey}', '${escapeJsString(
                formatCountryName(country2),
              )} Tree', '${escapeJsString(country2)}')">
              ✏️ Edit Tree
            </button>`
                : ""
            }
          </div>
        </div>
      `
        : "<div class='tree-diagram-empty'>Tree unavailable</div>";

    // ───── RENDER FINAL RESULT ─────
    resultDiv.innerHTML = `
      <div class="pipeline-steps">
        <div class="step done">1. Data Collection</div>
        <div class="step done">2. Tree Construction</div>
        <div class="step done">3. TED</div>
        <div class="step done">4. Edit Script</div>
        <div class="step done">5. Patching</div>
        <div class="step done">6. Output</div>
      </div>

      <div class="cmp-header">
        <div class="cmp-country-pill">
          <div class="cmp-country-label">${formatCountryName(country1)}</div>
          <div class="cmp-country-sub">Source tree</div>
        </div>

        <div class="cmp-score-center">
          <div class="cmp-score-ring" style="--c:${simColor}">
            <div class="cmp-score-pct">${simPct}%</div>
            <div class="cmp-score-word">Similarity</div>
          </div>
          <div class="cmp-ted">
            TED: <strong>${ted}</strong>
          </div>
        </div>

        <div class="cmp-country-pill">
          <div class="cmp-country-label">${formatCountryName(country2)}</div>
          <div class="cmp-country-sub">Target tree</div>
        </div>
      </div>

      <p class="cmp-algo-note">Chawathe TED (LD-pair + Dynamic Programming)</p>

      <div class="cmp-card">
        <div class="cmp-card-hdr">
          <span class="cmp-card-title">Step 1 — Tree Construction</span>
        </div>

        <details class="cmp-country-group" open>
          <summary>🌍 ${formatCountryName(country1)}</summary>
          <div class="cmp-country-group-body">
            <details class="cmp-collapse" open>
              <summary>🌳 Tree diagram</summary>
              <div class="cmp-collapse-body">${tree1Button}</div>
            </details>
            <details class="cmp-collapse">
              <summary>🧾 JSON</summary>
              <div class="cmp-collapse-body">
                ${renderCopyableJsonBlock(
                  `${formatCountryName(country1)} JSON`,
                  country1Doc,
                )}
              </div>
            </details>
          </div>
        </details>

        <details class="cmp-country-group" open>
          <summary>🌍 ${formatCountryName(country2)}</summary>
          <div class="cmp-country-group-body">
            <details class="cmp-collapse" open>
              <summary>🌳 Tree diagram</summary>
              <div class="cmp-collapse-body">${tree2Button}</div>
            </details>
            <details class="cmp-collapse">
              <summary>🧾 JSON</summary>
              <div class="cmp-collapse-body">
                ${renderCopyableJsonBlock(
                  `${formatCountryName(country2)} JSON`,
                  country2Doc,
                )}
              </div>
            </details>
          </div>
        </details>
      </div>

      <div class="cmp-card">
        <div class="cmp-card-hdr">
          <span class="cmp-card-title">Step 2 — Tree Edit Distance (TED)</span>
        </div>
        <div class="cmp-stat-row">
          <div class="cmp-stat-box">
            <div class="cmp-stat-num">${comp.tree1_size || 0}</div>
            <div class="cmp-stat-lbl">${formatCountryName(country1)} Nodes</div>
          </div>
          <div class="cmp-stat-box cmp-stat-mid">
            <div class="cmp-stat-num">${ted}</div>
            <div class="cmp-stat-lbl">TED Distance</div>
          </div>
          <div class="cmp-stat-box">
            <div class="cmp-stat-num">${comp.tree2_size || 0}</div>
            <div class="cmp-stat-lbl">${formatCountryName(country2)} Nodes</div>
          </div>
        </div>
      </div>

      <div class="cmp-card">
        <div class="cmp-card-hdr">
          <span class="cmp-card-title">Step 3 — Edit Script</span>
        </div>

        <div class="cmp-ops-badges" style="padding:16px 20px 0;">
          <span class="cmp-op-pill">Total: ${totalOperations}</span>
          <span class="cmp-op-pill op-match">Matches: ${opCounts.matches}</span>
          <span class="cmp-op-pill op-update">Updates: ${opCounts.updates}</span>
          <span class="cmp-op-pill op-insert">Inserts: ${opCounts.inserts}</span>
          <span class="cmp-op-pill op-delete">Deletes: ${opCounts.deletes}</span>
        </div>

        <div class="cmp-diff-table-wrap" style="padding:16px 16px 0;">
          <table class="cmp-diff-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Type</th>
                <th>Field</th>
                <th>${formatCountryName(country1)}</th>
                <th>${formatCountryName(country2)}</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              ${
                opRows ||
                "<tr><td colspan='6'>No non-matching operations found</td></tr>"
              }
            </tbody>
          </table>
        </div>

        <details class="cmp-collapse">
          <summary>📋 Full edit script (including matches)</summary>
          <div class="cmp-collapse-body">
            <table class="cmp-diff-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Type</th>
                  <th>Field</th>
                  <th>${formatCountryName(country1)}</th>
                  <th>${formatCountryName(country2)}</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>${fullRows}</tbody>
            </table>
          </div>
        </details>

        <details class="cmp-collapse">
          <summary>🧾 Edit script JSON</summary>
          <div class="cmp-collapse-body">
            ${renderCopyableJsonBlock("Edit Script JSON", es)}
          </div>
        </details>
      </div>

      <div style="padding: 20px 0;">
        <button
          type="button"
          id="patch-comparison-btn"
          class="btn btn-warning"
          onclick="patchCurrentComparison()">
          🧩 Patch
        </button>
      </div>

      <div id="patch-output-container" style="display:none;"></div>

      <div id="save-comparison-container" style="display:none;"></div>

    `;
  } catch (e) {
    hideLoading();
    console.error(e);
    resultDiv.innerHTML = `<div class="error-message"><h3>❌ Error</h3><p>${escapeHtml(
      e.message,
    )}</p></div>`;
  }
}

async function patchCurrentComparison() {
  if (!currentComparisonPatchState) {
    alert("Please run a comparison first.");
    return;
  }

  const { country1, country2 } = currentComparisonPatchState;

  const patchBtn = document.getElementById("patch-comparison-btn");
  const patchOutputContainer = document.getElementById(
    "patch-output-container",
  );
  const saveContainer = document.getElementById("save-comparison-container");

  if (patchBtn) {
    patchBtn.disabled = true;
    patchBtn.innerHTML = "⏳ Patching...";
  }

  patchOutputContainer.style.display = "block";
  patchOutputContainer.innerHTML = `
    <div class="cmp-card">
      <div class="cmp-card-hdr">
        <span class="cmp-card-title">Step 4 — Patched Output</span>
      </div>
      <div style="padding: 20px;">
        <p>⏳ Applying edit script and generating patched output...</p>
      </div>
    </div>
  `;

  try {
    const patchRes = await fetch(`${API_BASE}/patch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country1, country2, format: "all" }),
    });

    const patchData = await patchRes.json();

    console.log("[PATCH] patchData:", patchData);

    if (!patchData.success) {
      patchOutputContainer.innerHTML = `
        <div class="cmp-card">
          <div class="cmp-card-hdr">
            <span class="cmp-card-title">Step 4 — Patched Output</span>
          </div>
          <div class="error-message" style="margin:16px;">
            <h3>❌ Patching failed</h3>
            <p>${escapeHtml(patchData?.error || "Unknown patching error")}</p>
          </div>
        </div>
      `;

      if (patchBtn) {
        patchBtn.disabled = false;
        patchBtn.innerHTML = "🧩 Patch";
      }

      return;
    }

    const patchedTreeKey = patchData.patched_tree
      ? registerTreeImage(patchData.patched_tree)
      : null;

    currentPatchedJsonDoc = patchData.json_doc || null;

    patchOutputContainer.innerHTML = `
      <div class="cmp-card">
        <div class="cmp-card-hdr">
          <span class="cmp-card-title">Step 4 — Patched Output</span>
        </div>

        <div class="patch-output">
          <h4>✅ Patched Result: ${formatCountryName(country1)} → ${formatCountryName(country2)}</h4>

          <details class="cmp-collapse" open>
            <summary>📋 Infobox output</summary>
            <div class="cmp-collapse-body">
              <pre class="infobox-pre">${escapeHtml(patchData.infobox || "")}</pre>
            </div>
          </details>

          <details class="cmp-collapse">
            <summary>{ } Patched JSON document</summary>
            <div class="cmp-collapse-body">
              ${renderCopyableJsonBlock("Patched JSON Document", patchData.json_doc || "")}
            </div>
          </details>

          <details class="cmp-collapse">
            <summary>🌳 Patched tree</summary>
            <div class="cmp-collapse-body">
              ${
                patchData.patched_tree
                  ? `
                    <div class="tree-preview-card">
                      <p>Patched tree available as image preview.</p>
                      <button
                        type="button"
                        class="btn btn-primary"
                        onclick="openTreeImageModal('${patchedTreeKey}', 'Patched Tree')">
                        🌳 View Patched Tree
                      </button>
                    </div>
                  `
                  : "<div class='tree-diagram-empty'>Patched tree unavailable</div>"
              }
            </div>
          </details>

          <details class="cmp-collapse">
            <summary>🧾 Patched tree JSON</summary>
            <div class="cmp-collapse-body">
              ${renderCopyableJsonBlock("Patched Tree JSON", patchData.patched_tree || {})}
            </div>
          </details>
        </div>
      </div>
    `;

    saveContainer.style.display = "block";
    saveContainer.innerHTML = `
      <div class="save-comparison-section" style="margin-top: 20px; padding: 20px; background: #f3f4f6; border-radius: 8px; border-left: 4px solid #3b82f6;">
        <h3>💾 Save This Comparison</h3>
        <p style="color: #6b7280; margin-bottom: 16px;">
          Save the patched document as JSON with a unique name for later reference.
        </p>

        <div style="display: flex; gap: 12px; align-items: flex-end;">
          <div style="flex: 1; max-width: 300px;">
            <label for="comparison-name-input" style="display: block; font-weight: 600; margin-bottom: 8px;">
              Comparison Name:
            </label>
            <input
              type="text"
              id="comparison-name-input"
              placeholder="e.g. ${formatCountryName(country1)}_vs_${formatCountryName(country2)}_v1"
              style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px;">
          </div>

          <button
            type="button"
            class="btn btn-primary"
            id="save-comparison-btn"
            onclick="saveComparisonResult(currentPatchedJsonDoc)">
            💾 Save Comparison
          </button>
        </div>

        <div id="save-result" style="margin-top: 12px; display: none;"></div>
      </div>
    `;

    if (patchBtn) {
      patchBtn.disabled = true;
      patchBtn.innerHTML = "✅ Patched";
    }
  } catch (e) {
    console.error(e);

    patchOutputContainer.innerHTML = `
      <div class="cmp-card">
        <div class="cmp-card-hdr">
          <span class="cmp-card-title">Step 4 — Patched Output</span>
        </div>
        <div class="error-message" style="margin:16px;">
          <h3>❌ Error</h3>
          <p>${escapeHtml(e.message)}</p>
        </div>
      </div>
    `;

    if (patchBtn) {
      patchBtn.disabled = false;
      patchBtn.innerHTML = "🧩 Patch";
    }
  }
}

function formatTreeAsIndentedText(node, depth = 0) {
  if (!node) return "";

  const indent = "  ".repeat(depth);
  const label = node.label || "unknown";
  const type = node.node_type || node.type || "element";
  const value =
    node.value !== undefined &&
    node.value !== null &&
    String(node.value).trim() !== ""
      ? `: ${String(node.value)}`
      : "";

  const line = `${indent}${type === "text" ? "#text" : label}${value}`;
  const children = Array.isArray(node.children) ? node.children : [];

  if (!children.length) return line;

  return [
    line,
    ...children.map((child) => formatTreeAsIndentedText(child, depth + 1)),
  ].join("\n");
}

async function saveComparisonResult(patchedJson) {
  const nameInput = document.getElementById("comparison-name-input");
  const saveResultDiv = document.getElementById("save-result");
  const btn = document.getElementById("save-comparison-btn");
  const countryName = nameInput.value.trim();

  if (!countryName) {
    saveResultDiv.style.display = "block";
    saveResultDiv.innerHTML = `<div class="error-message" style="padding: 10px; background: #fee2e2; border: 1px solid #fca5a5; border-radius: 6px; color: #991b1b;">⚠️ Please enter a country name.</div>`;
    return;
  }

  // Validate name: alphanumeric, underscores, hyphens, spaces allowed
  if (!/^[a-zA-Z0-9_\- ]+$/.test(countryName)) {
    saveResultDiv.style.display = "block";
    saveResultDiv.innerHTML = `<div class="error-message" style="padding: 10px; background: #fee2e2; border: 1px solid #fca5a5; border-radius: 6px; color: #991b1b;">⚠️ Name can only contain letters, numbers, underscores, hyphens, and spaces.</div>`;
    return;
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "⏳ Saving...";

  try {
    // Ensure patchedJson is an object
    const jsonData =
      typeof patchedJson === "string" ? JSON.parse(patchedJson) : patchedJson;

    const response = await fetch(`${API_BASE}/comparisons/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        country_name: countryName, // Send as country_name
        patched_json: jsonData,
      }),
    });

    const data = await response.json();

    saveResultDiv.style.display = "block";

    if (data.success) {
      saveResultDiv.innerHTML = `
        <div class="success-message" style="padding: 10px; background: #dcfce7; border: 1px solid #86efac; border-radius: 6px; color: #166534;">
          ✅ ${data.message}
        </div>`;
      nameInput.value = "";
      nameInput.disabled = true;
      btn.disabled = true;
      btn.innerHTML = "✅ Saved";
    } else {
      saveResultDiv.innerHTML = `
        <div class="error-message" style="padding: 10px; background: #fee2e2; border: 1px solid #fca5a5; border-radius: 6px; color: #991b1b;">
          ❌ ${data.error}
        </div>`;
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  } catch (e) {
    console.error("Error saving comparison:", e);
    saveResultDiv.style.display = "block";
    saveResultDiv.innerHTML = `
      <div class="error-message" style="padding: 10px; background: #fee2e2; border: 1px solid #fca5a5; border-radius: 6px; color: #991b1b;">
        ❌ Error saving comparison: ${escapeHtml(e.message)}
      </div>`;
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

// ─────────────────────────────────────────────
//  Tree visualization for image modal
// ─────────────────────────────────────────────

const TREE_DEPTH_PALETTE = [
  { fill: "#dbeafe", stroke: "#2563eb", text: "#1e3a8a" },
  { fill: "#cffafe", stroke: "#0891b2", text: "#164e63" },
  { fill: "#d1fae5", stroke: "#059669", text: "#064e3b" },
  { fill: "#ede9fe", stroke: "#7c3aed", text: "#3b0764" },
  { fill: "#ffedd5", stroke: "#ea580c", text: "#7c2d12" },
  { fill: "#ffe4e6", stroke: "#e11d48", text: "#881337" },
  { fill: "#ccfbf1", stroke: "#0d9488", text: "#134e4a" },
  { fill: "#fef9c3", stroke: "#ca8a04", text: "#713f12" },
];

function treeDepthColor(depth) {
  return TREE_DEPTH_PALETTE[depth % TREE_DEPTH_PALETTE.length];
}

function toTitleCaseLabel(label) {
  const s = String(label || "").trim();
  if (!s) return "Unknown";

  const m = s.match(/^(.*)_(\d{4})$/);
  if (m) {
    const base = m[1]
      .split("_")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    return `${base} (${m[2]})`;
  }

  return s
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatTreeDisplayLabel(node) {
  const nodeType = String(node.node_type || node.type || "").toLowerCase();
  const nodeLabel = String(node.label || "").toLowerCase();
  const nodeValue = String(node.value || "");

  if (nodeType === "text" || nodeLabel === "#text") {
    return nodeValue || "#text";
  }

  if (nodeLabel === "item") return "entry";
  if (nodeLabel === "sub_item") return "detail";

  return toTitleCaseLabel(node.label || "unknown");
}

function buildDiagramTree(node, maxDepth = 100, depth = 0) {
  if (!node) return null;

  const nodeType = String(node.node_type || node.type || "").toLowerCase();
  const nodeLabel = String(node.label || "").toLowerCase();
  const isText = nodeType === "text" || nodeLabel === "#text";

  const displayLabel = formatTreeDisplayLabel(node);

  const result = {
    label: displayLabel,
    rawLabel: node.label || "unknown",
    rawValue: node.value || "",
    value: node.value || "",
    nodeType: node.node_type || node.type || "element",
    depth,
    children: [],
  };

  if (depth >= maxDepth) {
    const hiddenChildren = Array.isArray(node.children)
      ? node.children.length
      : 0;

    if (hiddenChildren > 0) {
      result.children.push({
        label: `+${hiddenChildren} more`,
        rawLabel: "more",
        rawValue: "",
        value: "",
        nodeType: "more",
        depth: depth + 1,
        children: [],
      });
    }

    return result;
  }

  const children = Array.isArray(node.children) ? node.children : [];
  result.children = children
    .map((child) => buildDiagramTree(child, maxDepth, depth + 1))
    .filter(Boolean);

  return result;
}

function measureTree(node) {
  if (!node) return { width: 0, height: 0 };
  if (!node.children || node.children.length === 0) {
    return { width: 1, height: 1 };
  }

  const childMeasures = node.children.map(measureTree);
  return {
    width: childMeasures.reduce((sum, c) => sum + c.width, 0),
    height: 1 + Math.max(...childMeasures.map((c) => c.height)),
  };
}

function layoutTree(node, depth = 0, xStart = 0, positions = []) {
  if (!node) return positions;
  const subtree = measureTree(node);
  const centerX = xStart + subtree.width / 2;
  positions.push({ node, x: centerX, y: depth + 1, depth });
  let cursor = xStart;
  for (const child of node.children || []) {
    layoutTree(child, depth + 1, cursor, positions);
    cursor += measureTree(child).width;
  }
  return positions;
}

function escapeSvg(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function generateTreeSvgMarkup(node, options = {}) {
  if (!node) {
    return `
      <svg xmlns="http://www.w3.org/2000/svg" width="600" height="160">
        <rect width="100%" height="100%" fill="#ffffff"/>
        <text x="50%" y="50%" text-anchor="middle" fill="#94a3b8" font-size="16">
          Tree unavailable
        </text>
      </svg>
    `;
  }

  const maxDepth = options.maxDepth ?? 100;
  const diagramTree = buildDiagramTree(node, maxDepth);
  const positions = layoutTree(diagramTree);
  const measure = measureTree(diagramTree);

  const unitX = 250;
  const unitY = 160;
  const marginX = 100;
  const marginY = 70;

  const getBox = (p) => ({
    width:
      p.node.nodeType === "more" ? 130 : p.node.nodeType === "text" ? 240 : 190,
    height: 68,
  });

  const positioned = positions.map((p) => ({
    ...p,
    px: marginX + (p.x - 0.5) * unitX,
    py: marginY + (p.y - 1) * unitY,
  }));

  const svgWidth = Math.max(520, measure.width * unitX + marginX * 2);
  const maxBottom = Math.max(
    ...positioned.map((p) => p.py + getBox(p).height / 2),
  );
  const svgHeight = Math.max(200, maxBottom + 60);

  const posMap = new Map();
  positioned.forEach((p) => posMap.set(p.node, p));

  const gradDefs = TREE_DEPTH_PALETTE.map(
    (c, i) => `
    <linearGradient id="ng${i}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="${c.fill}" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="${c.fill}" stop-opacity="1"/>
    </linearGradient>`,
  ).join("");

  const edges = positioned
    .flatMap((p) =>
      (p.node.children || []).map((child) => {
        const cp = posMap.get(child);
        if (!cp) return "";
        const pb = getBox(p);
        const cb = getBox(cp);
        const x1 = p.px;
        const y1 = p.py + pb.height / 2;
        const x2 = cp.px;
        const y2 = cp.py - cb.height / 2;
        const my = (y1 + y2) / 2;
        const col = treeDepthColor(p.depth).stroke;

        return `<path d="M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}"
          fill="none" stroke="${col}" stroke-width="2"
          stroke-opacity="0.45" stroke-linecap="round"/>`;
      }),
    )
    .join("");

  const nodesSvg = positioned
    .map((p) => {
      const nodeType = String(p.node.nodeType || "").toLowerCase();
      const nodeLabel = String(p.node.label || "").toLowerCase();

      const isText =
        nodeType === "text" || nodeType === "#text" || nodeLabel === "#text";

      const isMore = nodeType === "more";

      const box = getBox(p);
      const depth = p.node.depth ?? p.depth ?? 0;
      const col = treeDepthColor(depth);

      const x = p.px - box.width / 2;
      const y = p.py - box.height / 2;

      let fillAttr;
      let strokeAttr;
      let textFill;
      let badge;

      if (isMore) {
        fillAttr = "#f8fafc";
        strokeAttr = "#94a3b8";
        textFill = "#64748b";
        badge = "";
      } else if (isText) {
        fillAttr = "#fef3c7";
        strokeAttr = "#d97706";
        textFill = "#92400e";
        badge = `<rect x="${x + 5}" y="${y + 5}" rx="3" width="30" height="14"
                         fill="#fde68a" stroke="#d97706" stroke-width="0.8"/>
                   <text x="${x + 20}" y="${y + 14.5}" text-anchor="middle"
                         font-size="8" font-weight="800" fill="#92400e">TXT</text>`;
      } else {
        const gi = depth % TREE_DEPTH_PALETTE.length;
        fillAttr = `url(#ng${gi})`;
        strokeAttr = col.stroke;
        textFill = col.text;
        badge = `<circle cx="${x + box.width - 14}" cy="${y + 14}" r="10"
                            fill="${col.stroke}" fill-opacity="0.15"
                            stroke="${col.stroke}" stroke-width="1"/>
                   <text x="${x + box.width - 14}" y="${y + 18}"
                         text-anchor="middle" font-size="9" font-weight="800"
                         fill="${col.stroke}">${depth}</text>`;
      }

      const fullLabel = String(
        isText
          ? p.node.rawValue || p.node.value || p.node.label || ""
          : p.node.label || "",
      );

      const maxLen = isText ? 28 : isMore ? 14 : 20;
      const vis =
        fullLabel.length > maxLen
          ? fullLabel.slice(0, maxLen - 1) + "…"
          : fullLabel;

      return `<g>
        <title>${escapeSvg(fullLabel)}</title>
        <rect x="${x}" y="${y}" rx="10" ry="10"
              width="${box.width}" height="${box.height}"
              fill="${fillAttr}" stroke="${strokeAttr}" stroke-width="1.8"/>
        ${badge}
        <text x="${p.px}" y="${p.py + 6}" text-anchor="middle"
              font-family="'Cascadia Code','Fira Code',ui-monospace,monospace"
              font-size="12" font-weight="700" fill="${textFill}">
          ${escapeSvg(vis)}
        </text>
      </g>`;
    })
    .join("");

  return `
    <svg xmlns="http://www.w3.org/2000/svg"
         width="${svgWidth}" height="${svgHeight}"
         viewBox="0 0 ${svgWidth} ${svgHeight}">
      <rect width="100%" height="100%" fill="#ffffff"/>
      <defs>
        ${gradDefs}
      </defs>
      ${edges}
      ${nodesSvg}
    </svg>
  `;
}

function renderTreeDiagram(node, options = {}) {
  if (!node) return `<div class="tree-diagram-empty">Tree unavailable</div>`;
  const treeKey = registerTreeImage(node);
  return `
    <div class="tree-preview-card">
      <p>Full tree available as image preview.</p>
      <button
        type="button"
        class="btn btn-primary"
        onclick="openTreeImageModal('${treeKey}', 'Tree Preview')">
        🌳 View Full Tree
      </button>
    </div>
  `;
}

function handleTreeWheel() {}
function startTreePan() {}

// ─────────────────────────────────────────────
//  Legacy patch/tree functions kept harmless
// ─────────────────────────────────────────────

async function runFullPipeline(country1, country2) {
  await compareCountries(country1, country2);
}

async function runPatching(country1, country2) {
  await compareCountries(country1, country2);
}

async function viewTree() {
  // No-op now: trees are shown through image modal buttons
}

async function downloadEditScript(c1, c2, fmt) {
  if (fmt === "xml") {
    const data = await (
      await fetch(`${API_BASE}/edit-script/xml`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country1: c1, country2: c2 }),
      })
    ).blob();

    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${c1}_${c2}_edit_script.xml`;
    a.click();
  } else {
    const data = await (
      await fetch(`${API_BASE}/edit-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country1: c1, country2: c2, format: "json" }),
      })
    ).json();

    const blob = new Blob([JSON.stringify(data.edit_script, null, 2)], {
      type: "application/json",
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${c1}_${c2}_edit_script.json`;
    a.click();
  }
}

async function downloadPatch(c1, c2, fmt) {
  const data = await (
    await fetch(`${API_BASE}/patch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country1: c1, country2: c2, format: fmt }),
    })
  ).blob();

  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${c1}_${c2}_patched.${fmt}`;
  a.click();
}

// ─────────────────────────────────────────────
//  1 vs All Comparison
// ──────────���──────────────────────────────────

let compareAllData = {
  baseCountry: null,
  allResults: [],
  filteredResults: [],
};

async function populateBaseCountrySelect() {
  try {
    const response = await fetch("http://localhost:5000/api/countries");
    const data = await response.json();

    if (data.success) {
      const select = document.getElementById("base-country-select");
      select.innerHTML = '<option value="">-- Select Country --</option>';

      data.countries.forEach((country) => {
        const option = document.createElement("option");
        option.value = country;
        option.textContent = country;
        select.appendChild(option);
      });
    }
  } catch (error) {
    console.error("Error loading countries:", error);
  }
}

async function startCompareAll() {
  const baseCountrySelect = document.getElementById("base-country-select");
  const baseCountry = baseCountrySelect.value;

  if (!baseCountry) {
    alert("Please select a country");
    return;
  }

  compareAllData.baseCountry = baseCountry;

  // Show loading
  const resultsContainer = document.getElementById("compare-all-results");
  const loadingDiv = document.getElementById("compare-all-loading");
  const tableContainer = document.getElementById("compare-all-table-container");

  resultsContainer.style.display = "block";
  loadingDiv.style.display = "flex";
  tableContainer.innerHTML = "";

  document.getElementById("compare-all-title").textContent =
    `Comparing "${baseCountry}" against all countries...`;

  try {
    const response = await fetch("http://localhost:5000/api/compare-all", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        base_country: baseCountry,
      }),
    });

    const data = await response.json();

    if (data.success) {
      compareAllData.allResults = data.results;
      compareAllData.filteredResults = [...data.results];

      // Reset the limit select to "First 10"
      document.getElementById("results-limit-select").value = "10";

      displayCompareAllResults("10");

      document.getElementById("compare-all-title").textContent =
        `Results: "${baseCountry}" vs ${data.total_comparisons} countries`;

      loadingDiv.style.display = "none";
    } else {
      tableContainer.innerHTML = `
        <div class="error-message-compare-all">
          <h3>Error</h3>
          <p>${data.error}</p>
        </div>
      `;
      loadingDiv.style.display = "none";
    }
  } catch (error) {
    console.error("Error during comparison:", error);
    tableContainer.innerHTML = `
      <div class="error-message-compare-all">
        <h3>Error</h3>
        <p>${error.message}</p>
      </div>
    `;
    loadingDiv.style.display = "none";
  }
}

function filterCompareAllResults() {
  const limit = document.getElementById("results-limit-select").value;
  displayCompareAllResults(limit);
}

function displayCompareAllResults(limit) {
  const tableContainer = document.getElementById("compare-all-table-container");

  let resultsToDisplay = compareAllData.allResults;

  if (limit !== "all") {
    const limitNum = parseInt(limit);
    resultsToDisplay = compareAllData.allResults.slice(0, limitNum);
  }

  if (resultsToDisplay.length === 0) {
    tableContainer.innerHTML = `
      <div class="no-results-message">
        <p>No comparison results available</p>
      </div>
    `;
    return;
  }

  let tableHTML = `
    <div class="compare-all-table-wrapper">
      <table class="compare-all-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Country</th>
            <th>Similarity %</th>
            <th>TED Distance</th>
          </tr>
        </thead>
        <tbody>
  `;

  resultsToDisplay.forEach((result, index) => {
    const similarity = (result.similarity * 100).toFixed(2);
    const tedDistance = Math.round(result.ted_distance);
    const barWidth = Math.max(5, similarity);

    tableHTML += `
      <tr>
        <td class="rank">${index + 1}</td>
        <td class="country-name">${result.country}</td>
        <td class="similarity">
          <div class="similarity-bar">
            <div class="similarity-bar-fill" style="width: ${barWidth}%"></div>
            <div class="similarity-bar-text">${similarity}%</div>
          </div>
        </td>
        <td class="ted-distance">${tedDistance}</td>
      </tr>
    `;
  });

  tableHTML += `
        </tbody>
      </table>
    </div>
    <div style="margin-top: 16px; font-size: 0.9rem; color: var(--ink-soft);">
      Showing ${resultsToDisplay.length} of ${compareAllData.allResults.length} results
    </div>
  `;

  tableContainer.innerHTML = tableHTML;
}

// Initialize base country select when page loads
document.addEventListener("DOMContentLoaded", function () {
  populateBaseCountrySelect();
});

// Update the compareAllCountries function to redirect from comparison tab
function compareAllCountries() {
  const navBtn = document.querySelectorAll(".nav-btn")[2]; // "1 vs All" is the 3rd button
  openTab("compare-all", navBtn);
}

// ─────────────────────────────────────────────
//  Browse / search
// ─────────────────────────────────────────────

async function searchCountry() {
  const name = document.getElementById("search-country").value.trim();

  if (!name) {
    loadCountryList();
    return;
  }

  showLoading();

  try {
    const data = await (await fetch(`${API_BASE}/country/${name}`)).json();
    hideLoading();

    if (data.success) showCountryModal(data.data);
    else alert("Country not found: " + data.error);
  } catch (e) {
    hideLoading();
    alert("Error: " + e.message);
  }
}

function changeItemsPerPage() {
  browseState.itemsPerPage = parseInt(
    document.getElementById("items-per-page").value,
  );
  browseState.currentPage = 1;
  renderCountryList();
}

function goToPage(page) {
  const total = Math.ceil(
    browseState.allCountries.length / browseState.itemsPerPage,
  );
  browseState.currentPage = Math.max(1, Math.min(page, total));
  renderCountryList();
}

function renderCountryList() {
  const listDiv = document.getElementById("country-list");
  const countries = browseState.allCountries;

  if (!countries.length) {
    listDiv.innerHTML = "<h3>No Countries Available</h3>";
    return;
  }

  const total = Math.ceil(countries.length / browseState.itemsPerPage);
  const start = (browseState.currentPage - 1) * browseState.itemsPerPage;
  const current = countries.slice(start, start + browseState.itemsPerPage);

  listDiv.innerHTML = `
    <div class="browse-header">
      <h3>Available Countries (${countries.length} total)</h3>
      <div class="pagination-controls">
        <label>Show:
          <select id="items-per-page" onchange="changeItemsPerPage()">
            ${[10, 20, 30, 50, 100]
              .map(
                (n) =>
                  `<option ${browseState.itemsPerPage === n ? "selected" : ""} value="${n}">${n}</option>`,
              )
              .join("")}
          </select>
        </label>
      </div>
    </div>

    <div class="country-grid">
      ${current
        .map(
          (c) => `
            <div class="country-card" onclick="loadCountryDetails('${c}')">
              ${formatCountryName(c)}
            </div>
          `,
        )
        .join("")}
    </div>

    <div class="pagination">${buildPagination(browseState.currentPage, total)}</div>`;
}

function buildPagination(cur, total) {
  let html = '<div class="pagination-buttons">';

  html += `<button class="pagination-btn" onclick="goToPage(${cur - 1})" ${cur === 1 ? "disabled" : ""}>« Prev</button>`;

  const start = Math.max(1, cur - 2);
  const end = Math.min(total, start + 4);

  if (start > 1) {
    html += `<button class="pagination-btn" onclick="goToPage(1)">1</button>${start > 2 ? "<span>…</span>" : ""}`;
  }

  for (let i = start; i <= end; i++) {
    html += `<button class="pagination-btn ${i === cur ? "active" : ""}" onclick="goToPage(${i})">${i}</button>`;
  }

  if (end < total) {
    html += `${end < total - 1 ? "<span>…</span>" : ""}<button class="pagination-btn" onclick="goToPage(${total})">${total}</button>`;
  }

  html += `<button class="pagination-btn" onclick="goToPage(${cur + 1})" ${cur === total ? "disabled" : ""}>Next »</button>`;
  html += `</div><div class="pagination-info">Page ${cur} of ${total}</div>`;

  return html;
}

async function loadCountryList() {
  showLoading();

  try {
    const [countriesRes, comparisonsRes, editedRes] = await Promise.all([
      fetch(`${API_BASE}/countries`),
      fetch(`${API_BASE}/comparisons`),
      fetch(`${API_BASE}/edited-countries`),
    ]);

    const countriesData = await countriesRes.json();
    const comparisonsData = await comparisonsRes.json();
    const editedData = await editedRes.json();

    let allNames = [];

    if (countriesData.success && Array.isArray(countriesData.countries)) {
      allNames.push(...countriesData.countries);
    }

    if (comparisonsData.success && Array.isArray(comparisonsData.comparisons)) {
      allNames.push(...comparisonsData.comparisons);
    }

    // editedData is an array of objects -> convert to names
    if (Array.isArray(editedData)) {
      allNames.push(...editedData.map((x) => x.country_name).filter(Boolean));
    }

    allNames = [...new Set(allNames)].sort((a, b) => a.localeCompare(b));

    browseState.allCountries = allNames;
    browseState.currentPage = 1;
    renderCountryList();
  } catch (e) {
    console.error(e);
    document.getElementById("country-list").innerHTML =
      `<div class="error-message"><h3>❌ Error</h3><p>${e.message}</p></div>`;
  } finally {
    hideLoading();
  }
}

async function loadCountryDetails(name) {
  showLoading();

  try {
    const data = await (await fetch(`${API_BASE}/country/${name}`)).json();
    hideLoading();
    if (data.success) showCountryModal(data.data);
  } catch (e) {
    hideLoading();
    alert("Error: " + e.message);
  }
}

// ─────────────────────────────────────────────
//  Country modal
// ─────────────────────────────────────────────

function showCountryModal(d) {
  const modal = document.getElementById("country-modal");
  const content = document.getElementById("modal-country-content");

  let html = `
    <h2>${formatCountryName(d.country_name)}</h2>
    <p class="modal-meta"><strong>Source:</strong> <a href="${d.source_url}" target="_blank">Wikipedia</a></p>
    <p class="modal-meta"><strong>Scraped:</strong> ${new Date(d.scraped_at).toLocaleString()}</p>
    <h3>Infobox Fields:</h3>
    <table class="data-table">`;

  // ✅ USE for...in LOOP - preserves insertion order in modern JavaScript
  for (const fieldName in d.fields) {
    if (d.fields.hasOwnProperty(fieldName)) {
      const fieldValue = d.fields[fieldName];
      const hasNewlines = fieldValue.includes("\n");

      html += `<tr><td><strong>${fieldName}</strong></td><td class="${hasNewlines ? "hierarchy-cell" : ""}">
        ${
          hasNewlines
            ? fieldValue
                .split("\n")
                .map(
                  (l) => `<div class="hierarchy-line">${escapeHtml(l)}</div>`,
                )
                .join("")
            : escapeHtml(fieldValue)
        }</td></tr>`;
    }
  }

  html += "</table>";

  content.innerHTML = html;
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeCountryModal() {
  document.getElementById("country-modal").style.display = "none";
  document.body.style.overflow = "auto";
}

// ─────────────────────────────────────────────
//  Utilities
// ─────────────────────────────────────────────

function humanizeLabel(label) {
  if (!label) return "—";

  const s = String(label).trim();
  if (!s) return "—";

  return s
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function isTextNode(node) {
  const label = String(node?.label || "").toLowerCase();
  const type = String(node?.type || node?.node_type || "").toLowerCase();
  return label === "#text" || type === "text";
}

/**
 * Best-effort parent field resolver for text-node operations.
 * Works if backend includes parent_label / parent / path.
 */
function getParentFieldLabel(node) {
  if (!node) return null;

  if (node.parent_label) return node.parent_label;

  if (node.parent?.label) return node.parent.label;

  if (Array.isArray(node.path) && node.path.length >= 2) {
    return node.path[node.path.length - 2];
  }

  return null;
}

function getOperationFieldLabel(op) {
  const s = op?.source || {};
  const t = op?.target || {};

  const sLabel = s.label || null;
  const tLabel = t.label || null;

  const sIsText = isTextNode(s);
  const tIsText = isTextNode(t);

  // Text update/insert/delete: show parent field instead of #text
  if (sIsText || tIsText) {
    const parentLabel =
      getParentFieldLabel(s) ||
      getParentFieldLabel(t) ||
      (sIsText ? null : sLabel) ||
      (tIsText ? null : tLabel);

    if (parentLabel) return humanizeLabel(parentLabel);

    // fallback
    return "Text Value";
  }

  // Element rename/update: show source -> target if labels differ
  if (sLabel && tLabel && sLabel !== tLabel) {
    return `${humanizeLabel(sLabel)} → ${humanizeLabel(tLabel)}`;
  }

  return humanizeLabel(sLabel || tLabel || "—");
}

function escapeForAttribute(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function copyTextToClipboard(text, btn = null) {
  try {
    await navigator.clipboard.writeText(String(text ?? ""));

    if (btn) {
      const original = btn.innerHTML;
      btn.innerHTML = "✅ Copied";
      btn.disabled = true;

      setTimeout(() => {
        btn.innerHTML = original;
        btn.disabled = false;
      }, 1500);
    }
  } catch (e) {
    console.error("Copy failed:", e);
    alert("Failed to copy to clipboard.");
  }
}

function renderCopyableJsonBlock(title, value) {
  const jsonText =
    typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);

  return `
    <div class="copy-block">
      <div class="copy-block-header">
        <span class="copy-block-title">${escapeHtml(title)}</span>
        <button
          type="button"
          class="btn btn-secondary btn-copy-json"
          onclick="copyTextToClipboard(this.getAttribute('data-copy-text'), this)"
          data-copy-text="${escapeForAttribute(jsonText)}">
          📋 Copy
        </button>
      </div>
      <pre class="doc-pre">${escapeHtml(jsonText)}</pre>
    </div>
  `;
}

function escapeHtml(text) {
  return String(text).replace(
    /[&<>"']/g,
    (m) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[m],
  );
}

function escapeJsString(text) {
  return String(text)
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "");
}

// ─────────────────────────────────────────────
//  TREE EDITING MODAL
// ─────────────────────────────────────────────

// ─────────────────────────────────────────────
//  TREE EDITING MODAL
// ─────────────────────────────────────────────

let treeEditState = {
  currentTree: null,
  originalCountry: null,
  editedNodes: {},
  selectedNode: null,
};

function openTreeEditModal(treeKey, title, originalCountry) {
  try {
    const tree = treeImageStore[treeKey];
    if (!tree) {
      alert("Tree data not found.");
      return;
    }

    // ✅ JUST STORE THE RAW DATA - Python will handle the order
    treeEditState.currentTree = JSON.parse(JSON.stringify(tree));
    treeEditState.originalCountry = originalCountry;
    treeEditState.editedNodes = {};
    treeEditState.selectedNode = null;

    const modal = document.getElementById("tree-edit-modal");
    document.getElementById("tree-edit-title").textContent = `Edit ${title}`;
    document.getElementById("tree-edit-original").textContent =
      `From: ${originalCountry}`;

    renderEditableTree(treeEditState.currentTree);

    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
  } catch (e) {
    console.error("Error opening tree edit modal:", e);
    alert("Failed to open tree editor: " + e.message);
  }
}

function closeTreeEditModal() {
  const modal = document.getElementById("tree-edit-modal");
  if (modal) modal.style.display = "none";
  document.body.style.overflow = "auto";
  treeEditState = {
    currentTree: null,
    originalCountry: null,
    editedNodes: {},
    selectedNode: null,
  };
}

function renderEditableTree(flatJsonData, container = null, depth = 0) {
  if (!container) {
    const editContainer = document.getElementById("tree-edit-container");
    editContainer.innerHTML = "";
    container = editContainer;
  }

  if (!flatJsonData || typeof flatJsonData !== "object") return;

  // Handle flat JSON structure: { country_name, fields, source_url, scraped_at }
  if (
    flatJsonData.country_name &&
    (flatJsonData.fields || flatJsonData.fields_array)
  ) {
    // Root node
    const rootDiv = document.createElement("div");
    rootDiv.className = "tree-edit-node";
    rootDiv.style.marginLeft = "0px";

    const rootLabel = document.createElement("div");
    rootLabel.className = "tree-edit-node-label";

    const rootIcon = document.createElement("span");
    rootIcon.className = "node-icon";
    rootIcon.textContent = "📋";
    rootLabel.appendChild(rootIcon);

    const rootText = document.createElement("span");
    rootText.className = "node-text";
    rootText.textContent = `${flatJsonData.country_name} (Infobox)`;
    rootLabel.appendChild(rootText);

    rootDiv.appendChild(rootLabel);
    container.appendChild(rootDiv);

    // Render fields as child nodes IN ORIGINAL ORDER
    const fieldsDiv = document.createElement("div");
    fieldsDiv.className = "tree-edit-children";
    container.appendChild(fieldsDiv);

    // ✅ HANDLE BOTH ARRAY AND DICT FORMATS
    let fieldOrder;
    let fieldsObj;

    if (flatJsonData.fields_array && Array.isArray(flatJsonData.fields_array)) {
      // Array format: convert to order array
      fieldOrder = flatJsonData.fields_array.map((item) => item.key);
      fieldsObj = {};
      flatJsonData.fields_array.forEach((item) => {
        fieldsObj[item.key] = item.value;
      });
    } else if (flatJsonData.fields) {
      // Dict format: use _field_order if available
      fieldsObj = flatJsonData.fields;
      fieldOrder = flatJsonData._field_order
        ? flatJsonData._field_order
        : Object.keys(fieldsObj);
    } else {
      return;
    }

    // Create all nodes with order index
    const fieldNodes = [];
    fieldOrder.forEach((fieldName, index) => {
      const fieldValue = fieldsObj[fieldName];
      if (fieldValue !== undefined) {
        const nodeDiv = renderFieldNodeElement(
          fieldName,
          fieldValue,
          fieldsObj,
          index,
        );
        fieldNodes.push({ index, node: nodeDiv });
      }
    });

    // Append in correct order
    fieldNodes
      .sort((a, b) => a.index - b.index)
      .forEach(({ node }) => {
        fieldsDiv.appendChild(node);
      });

    return;
  }

  // Fallback for tree-like structures
  const nodeDiv = document.createElement("div");
  nodeDiv.className = "tree-edit-node";
  nodeDiv.style.marginLeft = depth * 20 + "px";
  nodeDiv.onclick = (e) => {
    e.stopPropagation();
    selectTreeNode(nodeDiv, flatJsonData);
  };

  const label = document.createElement("div");
  label.className = "tree-edit-node-label";

  const icon = document.createElement("span");
  icon.className = "node-icon";
  icon.textContent = flatJsonData.children?.length ? "📁" : "📄";
  label.appendChild(icon);

  const text = document.createElement("span");
  text.className = "node-text";
  text.textContent = flatJsonData.label || "unknown";
  label.appendChild(text);

  if (flatJsonData.value) {
    const value = document.createElement("span");
    value.className = "node-value";
    value.textContent =
      flatJsonData.value.substring(0, 30) +
      (flatJsonData.value.length > 30 ? "..." : "");
    label.appendChild(value);
  }

  nodeDiv.appendChild(label);
  container.appendChild(nodeDiv);

  nodeDiv._treeNode = flatJsonData;

  if (flatJsonData.children && flatJsonData.children.length > 0) {
    const childrenDiv = document.createElement("div");
    childrenDiv.className = "tree-edit-children";
    container.appendChild(childrenDiv);

    flatJsonData.children.forEach((child) => {
      renderEditableTree(child, childrenDiv, depth + 1);
    });
  }
}

function renderFieldNodeElement(fieldName, fieldValue, fieldsObj, orderIndex) {
  const nodeDiv = document.createElement("div");
  nodeDiv.className = "tree-edit-node";
  nodeDiv.style.marginLeft = "20px";
  nodeDiv.setAttribute("data-field-order", orderIndex); // ✅ PRESERVE ORDER

  const fieldObj = { name: fieldName, value: fieldValue };

  nodeDiv.onclick = (e) => {
    e.stopPropagation();
    selectTreeNode(nodeDiv, fieldObj);
  };

  const label = document.createElement("div");
  label.className = "tree-edit-node-label";

  const icon = document.createElement("span");
  icon.className = "node-icon";
  icon.textContent = "🔑";
  label.appendChild(icon);

  const text = document.createElement("span");
  text.className = "node-text";
  text.textContent = fieldName;
  label.appendChild(text);

  const value = document.createElement("span");
  value.className = "node-value";
  const displayValue =
    fieldValue.substring(0, 40) + (fieldValue.length > 40 ? "..." : "");
  value.textContent = displayValue;
  label.appendChild(value);

  nodeDiv.appendChild(label);

  nodeDiv._fieldObj = fieldObj;
  nodeDiv._fieldsRef = fieldsObj;

  return nodeDiv;
}

function selectTreeNode(nodeDiv, nodeData) {
  // Remove previous selection
  document.querySelectorAll(".tree-edit-node.selected").forEach((n) => {
    n.classList.remove("selected");
  });

  // Select this node
  nodeDiv.classList.add("selected");
  treeEditState.selectedNode = nodeData;

  // Show node editing options
  showNodeEditPanel(nodeData);
}

function showNodeEditPanel(nodeData) {
  const panel = document.getElementById("tree-edit-panel");
  if (!panel) return;

  // Handle field nodes
  if (nodeData.name && nodeData.value !== undefined) {
    let html = `
      <div style="padding: 12px; background: #f0f4f8; border-radius: 8px;">
        <p style="margin: 0 0 8px; font-weight: 600; color: #1a202c;">📝 Field Editor</p>
        <p style="margin: 0 0 4px; font-size: 0.85rem; color: #4a5568;">
          <strong>Field Name:</strong> ${escapeHtml(nodeData.name)}
        </p>
        <p style="margin: 0 0 12px; font-size: 0.85rem; color: #4a5568; word-break: break-all;">
          <strong>Value:</strong> ${escapeHtml(String(nodeData.value).substring(0, 100))}${String(nodeData.value).length > 100 ? "..." : ""}
        </p>
        
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <button class="btn btn-warning btn-sm" onclick="editFieldValue('${escapeForAttribute(nodeData.name)}')">✏️ Edit Value</button>
          <button class="btn btn-danger btn-sm" onclick="deleteField('${escapeForAttribute(nodeData.name)}')">🗑️ Delete Field</button>
        </div>
      </div>
    `;
    panel.innerHTML = html;
    return;
  }

  // Handle regular tree nodes
  let html = `
    <div style="padding: 12px; background: #f0f4f8; border-radius: 8px;">
      <p style="margin: 0 0 8px; font-weight: 600; color: #1a202c;">Selected Node</p>
      <p style="margin: 0 0 4px; font-size: 0.85rem; color: #4a5568;">
        <strong>Label:</strong> ${escapeHtml(nodeData.label || "N/A")}
      </p>
      <p style="margin: 0 0 12px; font-size: 0.85rem; color: #4a5568;">
        <strong>Value:</strong> ${escapeHtml(String(nodeData.value || "").substring(0, 50))}
      </p>
      
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <button class="btn btn-primary btn-sm" onclick="editNodeLabel()">✏️ Edit Label</button>
        <button class="btn btn-warning btn-sm" onclick="editNodeValue()">✏️ Edit Value</button>
        <button class="btn btn-danger btn-sm" onclick="deleteNode()">🗑️ Delete</button>
      </div>
    </div>
  `;

  panel.innerHTML = html;
}

function editFieldValue(fieldName) {
  if (!treeEditState.currentTree || !treeEditState.currentTree.fields) return;

  const currentValue = treeEditState.currentTree.fields[fieldName];
  const newValue = prompt(`Edit value for "${fieldName}":`, currentValue);

  if (newValue !== null) {
    treeEditState.currentTree.fields[fieldName] = newValue;
    rerenderEditableTree();
  }
}

function deleteField(fieldName) {
  if (!treeEditState.currentTree || !treeEditState.currentTree.fields) return;

  if (confirm(`Delete field "${fieldName}"?`)) {
    delete treeEditState.currentTree.fields[fieldName];
    rerenderEditableTree();
  }
}

function editNodeLabel() {
  if (!treeEditState.selectedNode) return;
  const newLabel = prompt("Enter new label:", treeEditState.selectedNode.label);
  if (newLabel !== null) {
    treeEditState.selectedNode.label = newLabel;
    rerenderEditableTree();
  }
}

function editNodeValue() {
  if (!treeEditState.selectedNode) return;
  const newValue = prompt(
    "Enter new value:",
    treeEditState.selectedNode.value || "",
  );
  if (newValue !== null) {
    treeEditState.selectedNode.value = newValue;
    rerenderEditableTree();
  }
}

function deleteNode() {
  if (!treeEditState.selectedNode) return;
  if (confirm("Delete this node? This cannot be undone.")) {
    deleteNodeRecursive(treeEditState.currentTree, treeEditState.selectedNode);
    treeEditState.selectedNode = null;
    rerenderEditableTree();
  }
}

function deleteNodeRecursive(parent, target) {
  if (!parent.children) return false;

  const index = parent.children.findIndex((child) => child === target);
  if (index !== -1) {
    parent.children.splice(index, 1);
    return true;
  }

  for (const child of parent.children) {
    if (deleteNodeRecursive(child, target)) return true;
  }
  return false;
}

function rerenderEditableTree() {
  renderEditableTree(treeEditState.currentTree);
  treeEditState.selectedNode = null;
  const panel = document.getElementById("tree-edit-panel");
  if (panel) panel.innerHTML = "";
}

async function saveEditedTree() {
  if (!treeEditState.currentTree || !treeEditState.originalCountry) {
    alert("No data to save");
    return;
  }

  if (!confirm("Save the edited tree?")) {
    return;
  }

  showLoading();

  try {
    const editedTree = JSON.parse(JSON.stringify(treeEditState.currentTree));

    console.log("[SAVE] Sending edited tree to server...");
    console.log("[SAVE] Country:", treeEditState.originalCountry);
    console.log(
      "[SAVE] Fields count:",
      Object.keys(editedTree.fields || {}).length,
    );

    const response = await fetch(`${API_BASE}/save-edited-tree`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        original_country: treeEditState.originalCountry,
        edited_tree: editedTree,
      }),
    });

    const data = await response.json();
    hideLoading();

    if (data.success) {
      alert(`✅ Tree saved as "${data.saved_name}"`);
      closeTreeEditModal();
      loadCountriesForComparison();
    } else {
      alert(`❌ Error: ${data.error}`);
    }
  } catch (e) {
    hideLoading();
    console.error("Error saving tree:", e);
    alert("Error saving tree: " + e.message);
  }
}

window.onclick = function (e) {
  const modal = document.getElementById("country-modal");
  const confirmModal = document.getElementById("confirm-modal");
  const bulkModal = document.getElementById("bulk-scrape-modal");
  const treeImageModal = document.getElementById("tree-image-modal");
  const treeEditModal = document.getElementById("tree-edit-modal");

  if (e.target === modal) closeCountryModal();
  if (e.target === confirmModal) closeConfirmModal(false);
  if (e.target === bulkModal) closeBulkModal("cancel");
  if (e.target === treeImageModal) closeTreeImageModal();
  if (e.target === treeEditModal) closeTreeEditModal();
};
