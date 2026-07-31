(() => {
  "use strict";

  const view = document.body.dataset.view || "index";
  const navItems = [
    ["index", "Overview", "index.html"],
    ["source", "Source lineage", "01_source_lineage_explorer.html"],
    ["ocr", "OCR", "02_ocr_explorer.html"],
    ["classification", "Classification", "03_page_classifier_explorer.html"],
    ["graph", "Graph", "04_graph_explorer.html"],
    ["vector", "Vector space", "05_vector_explorer.html"],
    ["engram", "Engram", "06_engram_explorer.html"],
    ["storage", "Storage", "07_storage_explorer.html"],
    ["retrieval", "Retrieval trace", "08_retrieval_trace_explorer.html"],
    ["validation", "Validation", "09_answer_validation_explorer.html"],
  ];

  const state = {
    catalog: null,
    dataset: null,
    manifest: null,
    cache: new Map(),
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function pretty(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  }

  function routeLabel(route) {
    const labels = {
      plain_text: "Normal text / procedure",
      table: "Table / illustrated parts list",
      image: "Image / diagram",
      blank: "Blank / nearly blank",
      unknown: "Unknown",
    };
    return labels[route] || String(route || "unknown").replaceAll("_", " ");
  }

  function routePill(route) {
    return `<span class="route-pill ${escapeHtml(route)}">${escapeHtml(routeLabel(route))}</span>`;
  }

  function statusClass(status) {
    const text = String(status || "").toUpperCase();
    if (["PASS", "TRUE", "READY", "OK"].some((token) => text.includes(token))) return "good";
    if (["FAIL", "FALSE", "ERROR", "MISSING"].some((token) => text.includes(token))) return "bad";
    return "warn";
  }

  function getDatasetSlug() {
    const params = new URLSearchParams(location.search);
    return params.get("dataset") || sessionStorage.getItem("traceNetVisualLabDataset") || state.catalog?.datasets?.[0]?.slug;
  }

  async function fetchJson(path) {
    const normalized = new URL(path, location.href).href;
    if (state.cache.has(normalized)) return state.cache.get(normalized);
    const response = await fetch(normalized, { cache: "no-store" });
    if (!response.ok) throw new Error(`Could not load ${path}: HTTP ${response.status}`);
    const data = await response.json();
    state.cache.set(normalized, data);
    return data;
  }

  async function loadArtifact(name) {
    const file = state.manifest.files?.[name];
    if (!file) throw new Error(`Dataset manifest does not define ${name}`);
    return fetchJson(`data/${state.dataset.slug}/${file}`);
  }

  function setPageTitle() {
    const title = document.body.dataset.title || "TRACE-Net Visual Lab";
    document.title = `${title} | TRACE-Net Visual Lab`;
  }

  function renderShell() {
    const title = document.body.dataset.title || "TRACE-Net Visual Lab";
    const subtitle = document.body.dataset.subtitle || "Inspect every stage of the evidence pipeline.";
    const root = $("#app");
    root.innerHTML = `
      <div class="site-shell">
        <header class="topbar">
          <div class="brand">
            <h1>${escapeHtml(title)}</h1>
            <p>${escapeHtml(subtitle)}</p>
          </div>
          <div class="controls">
            <label class="control">Dataset
              <select id="dataset-select" aria-label="Dataset"></select>
            </label>
          </div>
        </header>
        <nav class="nav" aria-label="Visual Lab stages">
          ${navItems.map(([key, label, href]) => `<a class="${key === view ? "active" : ""}" href="${href}">${escapeHtml(label)}</a>`).join("")}
        </nav>
        <div id="status-strip" class="status-strip"></div>
        <main id="view-root"><div class="notice">Loading Visual Lab data…</div></main>
        <footer class="footer">TRACE-Net Visual Lab · Presentation data only · Source-truth mutation and production writes are not allowed.</footer>
      </div>`;
  }

  function updateLinksForDataset(slug) {
    $$(".nav a").forEach((link) => {
      const url = new URL(link.href);
      url.searchParams.set("dataset", slug);
      link.href = url.pathname.split("/").pop() + url.search;
    });
  }

  function renderDatasetControls() {
    const select = $("#dataset-select");
    select.innerHTML = state.catalog.datasets
      .map((item) => `<option value="${escapeHtml(item.slug)}" ${item.slug === state.dataset.slug ? "selected" : ""}>${escapeHtml(item.label)} (${escapeHtml(item.page_count)})</option>`)
      .join("");
    select.addEventListener("change", () => {
      sessionStorage.setItem("traceNetVisualLabDataset", select.value);
      const url = new URL(location.href);
      url.searchParams.set("dataset", select.value);
      location.href = url.href;
    });
    updateLinksForDataset(state.dataset.slug);
  }

  function renderStatusStrip() {
    const m = state.manifest;
    const strip = $("#status-strip");
    strip.innerHTML = [
      `<span class="badge ${statusClass(m.quality_status)}">Dataset quality: ${escapeHtml(m.quality_status)}</span>`,
      `<span class="badge">Pages: ${escapeHtml(m.page_count)}</span>`,
      `<span class="badge">Graph: ${escapeHtml(m.graph_node_count)} nodes / ${escapeHtml(m.graph_edge_count)} edges</span>`,
      `<span class="badge">Vectors: ${escapeHtml(m.embedding_point_count)} × ${escapeHtml(m.embedding_dimension)}D</span>`,
      `<span class="badge">Engram: ${escapeHtml(m.engram_layer_count)}/6 layers</span>`,
      `<span class="badge ${m.production_write_attempt_count === 0 ? "good" : "bad"}">Production writes: ${escapeHtml(m.production_write_attempt_count)}</span>`,
    ].join("");
  }

  function metric(label, value, detail = "") {
    return `<div class="metric"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span>${detail ? `<span class="muted">${escapeHtml(detail)}</span>` : ""}</div>`;
  }

  function searchFilter(records, search, keys) {
    const needle = String(search || "").trim().toLowerCase();
    if (!needle) return records;
    return records.filter((record) => keys.some((key) => pretty(record[key]).toLowerCase().includes(needle)));
  }

  function routeBars(counts) {
    const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...entries.map(([, value]) => Number(value) || 0));
    return `<div class="bar-list">${entries.map(([route, value]) => `
      <div class="bar-row">
        <div>${routePill(route)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (Number(value) / max) * 100)}%"></div></div>
        <div>${escapeHtml(value)}</div>
      </div>`).join("")}</div>`;
  }

  async function renderIndex() {
    const m = state.manifest;
    const stages = [
      ["01", "Source lineage", "Follow every page from the original TIFF through canonical identity and storage eligibility.", "01_source_lineage_explorer.html"],
      ["02", "OCR", "Compare browser-safe page thumbnails with Tesseract output, PSM attempts, identifiers, and text metrics.", "02_ocr_explorer.html"],
      ["03", "Classification", "See initial route clues, validation, retry decisions, final route, and graph-only holds.", "03_page_classifier_explorer.html"],
      ["04", "Graph", `Explore ${m.graph_node_count} nodes and ${m.graph_edge_count} typed relationships without touching production graph data.`, "04_graph_explorer.html"],
      ["05", "Vector space", `Inspect a 2D PCA view of ${m.embedding_point_count} real ${m.embedding_dimension}-dimensional BGE-M3 vectors.`, "05_vector_explorer.html"],
      ["06", "Engram", "Open the Working, Semantic, Procedural, Episodic, Trait, and Critic memory layers.", "06_engram_explorer.html"],
      ["07", "Storage plan", "Compare graph, Qdrant, and exact-search eligibility and inspect safety holds and zero-write enforcement.", "07_storage_explorer.html"],
      ["08", "Retrieval trace", "Replay deterministic extraction, route choice, vector guidance, graph expansion, evidence packaging, and Gemma.", "08_retrieval_trace_explorer.html"],
      ["09", "Answer validation", "Inspect final evidence checks, identifier fidelity, citation labels, release decisions, and safe abstentions.", "09_answer_validation_explorer.html"],
    ];
    $("#view-root").innerHTML = `
      <section class="grid cols-4" style="margin-bottom:16px">
        ${metric("Pages", m.page_count)}
        ${metric("Graph", `${m.graph_node_count} / ${m.graph_edge_count}`, "nodes / edges")}
        ${metric("Vectors", m.embedding_point_count, `${m.embedding_dimension} dimensions each`)}
        ${metric("Questions", m.question_count)}
      </section>
      <section class="panel" style="margin-bottom:16px">
        <h2>Final page routes</h2>
        ${routeBars(m.route_counts)}
      </section>
      <section class="stage-grid">
        ${stages.map(([number, title, description, href]) => `<a class="stage-card" href="${href}?dataset=${encodeURIComponent(state.dataset.slug)}"><span class="stage-number">STAGE ${number}</span><h2>${escapeHtml(title)}</h2><p>${escapeHtml(description)}</p><span class="muted">Open explorer →</span></a>`).join("")}
      </section>`;
  }

  async function renderSource() {
    const payload = await loadArtifact("source_lineage");
    const records = payload.records || [];
    const root = $("#view-root");
    root.innerHTML = `
      <div class="grid cols-2">
        <section class="panel">
          <div class="controls"><label class="control" style="width:100%">Search page, TIFF, or SHA-256<input id="source-search" placeholder="341, t_p_..., 00000341.tif"></label></div>
          <div id="source-table" class="table-wrap" style="margin-top:12px"></div>
        </section>
        <section class="panel"><h2>Selected page lineage</h2><div id="source-detail" class="notice">Select a page.</div></section>
      </div>`;

    const renderTable = () => {
      const filtered = searchFilter(records, $("#source-search").value, ["page_id", "source_member", "source_image_sha256"]);
      $("#source-table").innerHTML = `<table><thead><tr><th>Page</th><th>TIFF</th><th>Lineage</th><th>Storage</th></tr></thead><tbody>${filtered.map((r) => `<tr data-page-id="${escapeHtml(r.page_id)}"><td>${escapeHtml(r.page_number)}<br><span class="muted">${escapeHtml(r.page_id)}</span></td><td>${escapeHtml(r.source_member)}</td><td>${r.lineage_ready ? "✓ Ready" : "✗ Missing"}</td><td>G:${r.graph_ready ? "Y" : "N"} V:${r.vector_eligible ? "Y" : "N"} X:${r.exact_search_eligible ? "Y" : "N"}</td></tr>`).join("")}</tbody></table>`;
      $$("tr[data-page-id]", $("#source-table")).forEach((row) => row.addEventListener("click", () => show(records.find((r) => r.page_id === row.dataset.pageId))));
    };

    const show = (r) => {
      if (!r) return;
      $("#source-detail").className = "";
      $("#source-detail").innerHTML = `
        <div class="flow">
          <div class="flow-node"><div class="k">Run dataset</div><div class="v">${escapeHtml(state.dataset.label)}</div></div><div class="flow-arrow">→</div>
          <div class="flow-node"><div class="k">Original TIFF member</div><div class="v">${escapeHtml(r.source_member)}</div></div><div class="flow-arrow">→</div>
          <div class="flow-node"><div class="k">Canonical page ID</div><div class="v">${escapeHtml(r.page_id)}</div></div><div class="flow-arrow">→</div>
          <div class="flow-node"><div class="k">OCR hash</div><div class="v">${escapeHtml(r.ocr_text_sha256 || "—")}</div></div>
        </div>
        <div class="grid cols-2" style="margin-top:14px">
          ${metric("Lineage ready", r.lineage_ready ? "YES" : "NO")}
          ${metric("Source bytes", r.source_image_byte_count || "—")}
          ${metric("Graph ready", r.graph_ready ? "YES" : "NO")}
          ${metric("Vector eligible", r.vector_eligible ? "YES" : "NO")}
          ${metric("Exact-search eligible", r.exact_search_eligible ? "YES" : "NO")}
          ${metric("Source SHA-256", (r.source_image_sha256 || "—").slice(0, 16) + (r.source_image_sha256 ? "…" : ""))}
        </div>
        <h3 style="margin-top:14px">Full source reference</h3><pre>${escapeHtml(JSON.stringify(r, null, 2))}</pre>`;
      $$("tr", $("#source-table")).forEach((row) => row.classList.toggle("selected", row.dataset.pageId === r.page_id));
    };

    $("#source-search").addEventListener("input", renderTable);
    renderTable();
    show(records[0]);
  }

  async function renderOcr() {
    const payload = await loadArtifact("ocr_pages");
    const records = payload.records || [];
    const root = $("#view-root");
    root.innerHTML = `
      <section class="panel" style="margin-bottom:16px">
        <div class="controls">
          <label class="control">Page<select id="ocr-page"></select></label>
          <label class="control">Search OCR text<input id="ocr-search" placeholder="part number, warning, figure"></label>
        </div>
      </section>
      <section class="ocr-layout">
        <div class="panel"><h2>Browser display copy</h2><div id="ocr-image"></div><p class="muted">The PNG is only a viewing copy. The TIFF member and SHA-256 remain the evidence reference.</p></div>
        <div class="panel"><h2>OCR result</h2><div id="ocr-metrics" class="grid cols-3"></div><pre id="ocr-text"></pre></div>
      </section>`;
    const select = $("#ocr-page");
    select.innerHTML = records.map((r, i) => `<option value="${i}">${escapeHtml(String(r.page_number).padStart(3, "0"))} · ${escapeHtml(r.page_id)}</option>`).join("");

    const show = (index) => {
      const r = records[Number(index)] || records[0];
      if (!r) return;
      $("#ocr-image").innerHTML = r.thumbnail ? `<img class="page-image" src="${escapeHtml(r.thumbnail)}" alt="Scanned page ${escapeHtml(r.page_number)}">` : `<div class="no-image">No PNG thumbnail was exported.<br>Rebuild the dataset with <code>--copy-thumbnails</code>.</div>`;
      $("#ocr-metrics").innerHTML = [
        metric("OCR status", r.ocr_status), metric("Characters", r.ocr_text_char_count), metric("Words", r.ocr_text_word_count),
        metric("Best PSM", r.best_psm || "—"), metric("Part numbers", (r.part_numbers || []).length), metric("Table keywords", r.table_keyword_count || 0),
      ].join("");
      const needle = $("#ocr-search").value.trim();
      let text = r.ocr_text || "No OCR text.";
      if (needle) {
        const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        text = text.replace(new RegExp(escaped, "gi"), (match) => `[[${match}]]`);
      }
      $("#ocr-text").textContent = text;
    };
    select.addEventListener("change", () => show(select.value));
    $("#ocr-search").addEventListener("input", () => show(select.value));
    show(0);
  }

  async function renderClassification() {
    const payload = await loadArtifact("classification");
    const records = payload.records || [];
    const counts = payload.summary?.route_counts || {};
    $("#view-root").innerHTML = `
      <div class="grid cols-2">
        <section class="panel"><h2>Final route distribution</h2>${routeBars(counts)}</section>
        <section class="panel"><h2>Filters</h2><div class="controls"><label class="control">Route<select id="class-route"><option value="">All routes</option>${Object.keys(counts).map((r) => `<option>${escapeHtml(r)}</option>`).join("")}</select></label><label class="control">Search<input id="class-search" placeholder="page ID or reason"></label><label class="control"><span>Safety view</span><select id="class-hold"><option value="">All pages</option><option value="hold">Graph-only holds</option><option value="retrieval">Retrieval validated</option></select></label></div></section>
      </div>
      <section class="panel" style="margin-top:16px"><div id="class-table" class="table-wrap"></div></section>
      <section class="panel" style="margin-top:16px"><h2>Selected classification journey</h2><div id="class-detail" class="notice">Select a page.</div></section>`;

    const filtered = () => records.filter((r) => {
      const routeOk = !$("#class-route").value || r.final_route === $("#class-route").value;
      const holdMode = $("#class-hold").value;
      const holdOk = !holdMode || (holdMode === "hold" ? r.graph_only_safety_hold : r.retrieval_validated);
      const search = $("#class-search").value.toLowerCase();
      const searchOk = !search || JSON.stringify(r).toLowerCase().includes(search);
      return routeOk && holdOk && searchOk;
    });

    const show = (r) => {
      if (!r) return;
      $("#class-detail").className = "";
      const steps = [
        ["Initial route", r.initial_route], ["Four-route resolver", r.operational_route], ["Validated route", r.validated_route], ["Retry decision", r.retry_status || "not required"], ["Final visible route", r.final_route], ["Storage status", r.graph_only_safety_hold ? "GRAPH-ONLY SAFETY HOLD" : "VALIDATED FOR NORMAL PROCESSING"],
      ];
      $("#class-detail").innerHTML = `<div class="flow">${steps.map(([k, v], i) => `${i ? '<div class="flow-arrow">→</div>' : ""}<div class="flow-node"><div class="k">${escapeHtml(k)}</div><div class="v">${k.includes("route") ? routePill(v) : escapeHtml(v)}</div></div>`).join("")}</div><div class="grid cols-3" style="margin-top:14px">${metric("Page", r.page_id)}${metric("Validation score", r.final_validation_score || "—")}${metric("Graph-only hold", r.graph_only_safety_hold ? "YES" : "NO")}</div><h3 style="margin-top:14px">Deterministic reasons</h3><pre>${escapeHtml(pretty(r.reasons))}</pre>`;
    };

    const draw = () => {
      const rows = filtered();
      $("#class-table").innerHTML = `<table><thead><tr><th>Page</th><th>Initial</th><th>Final</th><th>Score</th><th>Safety</th></tr></thead><tbody>${rows.map((r) => `<tr data-page-id="${escapeHtml(r.page_id)}"><td>${escapeHtml(r.page_number)}<br><span class="muted">${escapeHtml(r.page_id)}</span></td><td>${routePill(r.initial_route)}</td><td>${routePill(r.final_route)}</td><td>${escapeHtml(r.final_validation_score ?? "—")}</td><td>${r.graph_only_safety_hold ? '<span class="badge warn">Graph-only</span>' : '<span class="badge good">Retrieval ready</span>'}</td></tr>`).join("")}</tbody></table>`;
      $$("tr[data-page-id]", $("#class-table")).forEach((row) => row.addEventListener("click", () => show(records.find((r) => r.page_id === row.dataset.pageId))));
    };
    ["#class-route", "#class-search", "#class-hold"].forEach((id) => $(id).addEventListener("input", draw));
    draw();
    show(records[0]);
  }

  function routeColor(route) {
    const styles = getComputedStyle(document.documentElement);
    return {
      plain_text: styles.getPropertyValue("--plain").trim(),
      table: styles.getPropertyValue("--table").trim(),
      image: styles.getPropertyValue("--image").trim(),
      blank: styles.getPropertyValue("--blank").trim(),
    }[route] || styles.getPropertyValue("--accent").trim();
  }

  async function renderGraph() {
    const [nodesPayload, edgesPayload] = await Promise.all([loadArtifact("graph_nodes"), loadArtifact("graph_edges")]);
    const allNodes = nodesPayload.records || [];
    const allEdges = edgesPayload.records || [];
    $("#view-root").innerHTML = `
      <section class="panel" style="margin-bottom:16px"><div class="controls"><label class="control">Search node<input id="graph-search" placeholder="part, page, manual"></label><label class="control">Node limit<select id="graph-limit"><option>200</option><option>500</option><option selected>1000</option><option value="999999">All</option></select></label></div><p class="muted">The explorer uses a deterministic clustered layout for presentation. It does not alter graph topology.</p></section>
      <section class="grid cols-3" style="margin-bottom:16px">${metric("Nodes", allNodes.length)}${metric("Edges", allEdges.length)}${metric("Production graph writes", 0)}</section>
      <section class="canvas-wrap"><canvas id="graph-canvas" width="1400" height="760"></canvas><div class="canvas-help">Drag to pan · mouse wheel to zoom · click a node to inspect it</div></section>
      <section class="panel" style="margin-top:16px"><h2>Selected node</h2><pre id="graph-detail">Click a node.</pre></section>`;

    const canvas = $("#graph-canvas");
    const ctx = canvas.getContext("2d");
    let panX = 0, panY = 0, scale = 1, dragging = false, lastX = 0, lastY = 0;
    let drawn = [];

    const nodeType = (n) => String(n.type || "unknown").toLowerCase();
    const nodeColor = (n) => {
      const type = nodeType(n);
      if (type.includes("page")) return routeColor("plain_text");
      if (type.includes("part")) return routeColor("table");
      if (type.includes("figure") || type.includes("visual")) return routeColor("image");
      if (type.includes("memory") || type.includes("engram")) return "#ffc766";
      return "#8290a6";
    };

    function buildLayout() {
      const search = $("#graph-search").value.toLowerCase().trim();
      const limit = Number($("#graph-limit").value);
      let nodes = allNodes;
      if (search) nodes = nodes.filter((n) => JSON.stringify(n).toLowerCase().includes(search));
      nodes = nodes.slice(0, limit);
      const idSet = new Set(nodes.map((n) => n.id));
      const groups = new Map();
      nodes.forEach((n) => {
        const key = nodeType(n).split(/[ _:]/)[0] || "other";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(n);
      });
      const groupEntries = [...groups.entries()];
      drawn = [];
      groupEntries.forEach(([group, groupNodes], groupIndex) => {
        const angle = (groupIndex / Math.max(1, groupEntries.length)) * Math.PI * 2;
        const cx = canvas.width / 2 + Math.cos(angle) * 250;
        const cy = canvas.height / 2 + Math.sin(angle) * 220;
        groupNodes.forEach((node, i) => {
          const a = (i / Math.max(1, groupNodes.length)) * Math.PI * 2 + angle;
          const radius = 28 + Math.sqrt(i) * 19;
          drawn.push({ node, x: cx + Math.cos(a) * radius, y: cy + Math.sin(a) * radius, r: search ? 7 : 4 });
        });
      });
      const position = new Map(drawn.map((d) => [d.node.id, d]));
      const edges = allEdges.filter((e) => idSet.has(e.source) && idSet.has(e.target));
      return { edges, position };
    }

    function draw() {
      const { edges, position } = buildLayout();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.translate(panX, panY); ctx.scale(scale, scale);
      ctx.strokeStyle = "rgba(99,137,181,.18)"; ctx.lineWidth = .8 / scale;
      edges.slice(0, 8000).forEach((e) => {
        const s = position.get(e.source), t = position.get(e.target); if (!s || !t) return;
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
      });
      drawn.forEach((d) => { ctx.fillStyle = nodeColor(d.node); ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fill(); });
      ctx.restore();
    }

    function canvasPoint(event) {
      const rect = canvas.getBoundingClientRect();
      const sx = canvas.width / rect.width, sy = canvas.height / rect.height;
      return { x: ((event.clientX - rect.left) * sx - panX) / scale, y: ((event.clientY - rect.top) * sy - panY) / scale };
    }
    canvas.addEventListener("mousedown", (e) => { dragging = true; lastX = e.clientX; lastY = e.clientY; });
    window.addEventListener("mouseup", () => { dragging = false; });
    window.addEventListener("mousemove", (e) => { if (!dragging) return; panX += (e.clientX - lastX) * (canvas.width / canvas.clientWidth); panY += (e.clientY - lastY) * (canvas.height / canvas.clientHeight); lastX = e.clientX; lastY = e.clientY; draw(); });
    canvas.addEventListener("wheel", (e) => { e.preventDefault(); scale = Math.max(.25, Math.min(4, scale * (e.deltaY < 0 ? 1.12 : .89))); draw(); }, { passive: false });
    canvas.addEventListener("click", (e) => { if (Math.abs(e.clientX - lastX) > 4 || Math.abs(e.clientY - lastY) > 4) return; const p = canvasPoint(e); const hit = drawn.find((d) => Math.hypot(p.x - d.x, p.y - d.y) < Math.max(10 / scale, d.r + 4)); if (hit) $("#graph-detail").textContent = JSON.stringify(hit.node, null, 2); });
    $("#graph-search").addEventListener("input", draw); $("#graph-limit").addEventListener("change", draw);
    draw();
  }

  async function renderVector() {
    const payload = await loadArtifact("vector_projection");
    const points = payload.records || [];
    const summary = payload.summary || {};
    $("#view-root").innerHTML = `
      <section class="notice" style="margin-bottom:16px">${escapeHtml(summary.visualization_warning || "This is a two-dimensional projection; the original vectors are unchanged.")}</section>
      <section class="grid cols-4" style="margin-bottom:16px">${metric("Points", summary.point_count || points.length)}${metric("Dimensions", summary.dimension || "—")}${metric("Projection", "PCA")}${metric("Model", points[0]?.model || "bge-m3")}</section>
      <section class="panel" style="margin-bottom:16px"><div class="controls"><label class="control">Route<select id="vector-route"><option value="">All routes</option>${[...new Set(points.map((p) => p.route))].map((r) => `<option>${escapeHtml(r)}</option>`).join("")}</select></label><label class="control">Search page<input id="vector-search" placeholder="page ID"></label></div><div class="legend" style="margin-top:12px"><span class="plain_text"><i></i>Normal text</span><span class="table"><i></i>Table/IPL</span><span class="image"><i></i>Image</span><span class="blank"><i></i>Blank</span></div></section>
      <section class="canvas-wrap"><canvas id="vector-canvas" width="1400" height="760"></canvas><div class="canvas-help">Hover or click a point · filtered points stay in their original PCA positions</div></section>
      <section class="grid cols-2" style="margin-top:16px"><div class="panel"><h2>Selected vector</h2><pre id="vector-detail">Click a point.</pre></div><div class="panel"><h2>Nearest displayed neighbors</h2><div id="vector-neighbors" class="notice">Select a point.</div></div></section>`;
    const canvas = $("#vector-canvas"), ctx = canvas.getContext("2d");
    let visible = points;
    function coordinates(p) { return { x: 70 + ((Number(p.x) + 1) / 2) * (canvas.width - 140), y: 50 + (1 - (Number(p.y) + 1) / 2) * (canvas.height - 100) }; }
    function filter() { const route = $("#vector-route").value; const search = $("#vector-search").value.toLowerCase(); visible = points.filter((p) => (!route || p.route === route) && (!search || p.page_id.toLowerCase().includes(search))); draw(); }
    function draw() { ctx.clearRect(0,0,canvas.width,canvas.height); ctx.strokeStyle="rgba(99,137,181,.25)"; ctx.beginPath(); ctx.moveTo(canvas.width/2,30); ctx.lineTo(canvas.width/2,canvas.height-30); ctx.moveTo(30,canvas.height/2); ctx.lineTo(canvas.width-30,canvas.height/2); ctx.stroke(); visible.forEach((p) => { const c=coordinates(p); ctx.fillStyle=routeColor(p.route); ctx.globalAlpha=.78; ctx.beginPath(); ctx.arc(c.x,c.y,$("#vector-search").value ? 7 : 4,0,Math.PI*2); ctx.fill(); }); ctx.globalAlpha=1; }
    function hit(event) { const rect=canvas.getBoundingClientRect(), x=(event.clientX-rect.left)*(canvas.width/rect.width), y=(event.clientY-rect.top)*(canvas.height/rect.height); return visible.reduce((best,p)=>{const c=coordinates(p),d=Math.hypot(x-c.x,y-c.y); return d<(best?.d??12)?{p,d}:best;},null)?.p; }
    function select(p) { if(!p)return; $("#vector-detail").textContent=JSON.stringify(p,null,2); const neighbors=points.filter((q)=>q.page_id!==p.page_id).map((q)=>({q,d:Math.hypot(Number(q.x)-Number(p.x),Number(q.y)-Number(p.y))})).sort((a,b)=>a.d-b.d).slice(0,5); $("#vector-neighbors").className=""; $("#vector-neighbors").innerHTML=`<div class="check-list">${neighbors.map(({q,d})=>`<div class="check"><span>${escapeHtml(q.page_id)}<br>${routePill(q.route)}</span><span>${d.toFixed(4)}<br><span class="muted">2D distance</span></span></div>`).join("")}</div><p class="muted">Nearest points here are based on the 2D display projection, not the original cosine similarity.</p>`; }
    canvas.addEventListener("click", (e)=>select(hit(e))); $("#vector-route").addEventListener("change",filter); $("#vector-search").addEventListener("input",filter); filter();
  }

  async function renderEngram() {
    const payload = await loadArtifact("engram_layers");
    const layers = payload.layers || [];
    $("#view-root").innerHTML = `
      <section class="notice" style="margin-bottom:16px">Engram separates current context, stable facts, operating rules, run history, answer behavior, and criticism so one memory type cannot silently impersonate another.</section>
      <section class="memory-grid">${layers.map((layer, i) => `<article class="memory-card"><h3><span class="memory-index">${i+1}</span>${escapeHtml(layer.name || layer.id || `Layer ${i+1}`)}</h3><pre>${escapeHtml(pretty(layer.content ?? layer))}</pre></article>`).join("")}</section>
      <section class="panel" style="margin-top:16px"><h2>Question movement through Engram</h2><div class="flow"><div class="flow-node"><div class="k">Question arrives</div><div class="v">Working memory</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Rules selected</div><div class="v">Procedural memory</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Facts retrieved</div><div class="v">Semantic memory</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Run recorded</div><div class="v">Episodic memory</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Answer checked</div><div class="v">Critic memory</div></div></div></section>`;
  }

  async function renderStorage() {
    const payload = await loadArtifact("storage_plan");
    const records = payload.records || [], s = payload.summary || {};
    $("#view-root").innerHTML = `
      <section class="grid cols-4" style="margin-bottom:16px">${metric("Graph-ready", s.graph_ready_count)}${metric("Vector eligible", s.vector_eligible_count)}${metric("Exact-search eligible", s.exact_search_eligible_count)}${metric("Production writes", s.production_write_attempt_count)}</section>
      <section class="notice" style="margin-bottom:16px">These are read-only eligibility records. A page can remain graph-visible while being blocked from Qdrant or exact search.</section>
      <section class="panel"><div class="controls"><label class="control">Search page<input id="storage-search" placeholder="page ID"></label><label class="control">Eligibility<select id="storage-filter"><option value="">All</option><option value="hold">Graph-only safety holds</option><option value="vector">Vector eligible</option><option value="exact">Exact-search eligible</option></select></label></div><div id="storage-table" class="table-wrap" style="margin-top:12px"></div></section>`;
    const draw=()=>{const search=$("#storage-search").value.toLowerCase(), mode=$("#storage-filter").value; const filtered=records.filter(r=>(!search||r.page_id.toLowerCase().includes(search))&&(!mode||(mode==="hold"&&r.graph_only_safety_hold)||(mode==="vector"&&r.vector_eligible)||(mode==="exact"&&r.exact_search_eligible))); $("#storage-table").innerHTML=`<table><thead><tr><th>Page</th><th>Route</th><th>Graph</th><th>Qdrant</th><th>Exact</th><th>Reason</th></tr></thead><tbody>${filtered.map(r=>`<tr><td>${escapeHtml(r.page_id)}</td><td>${routePill(r.final_route)}</td><td>${r.graph_ready?"✓":"—"}</td><td>${r.vector_eligible?"✓":"BLOCKED"}</td><td>${r.exact_search_eligible?"✓":"BLOCKED"}</td><td>${escapeHtml(r.reason)}</td></tr>`).join("")}</tbody></table>`;}; $("#storage-search").addEventListener("input",draw); $("#storage-filter").addEventListener("change",draw); draw();
  }

  function normalizedEvidence(record) {
    const id = record.evidence_id || record.citation_id || record.id || record.label || "Evidence";
    const page = record.page_id || record.page || record.canonical_page_id || "—";
    const route = record.route || record.final_route || record.operational_route || "unknown";
    const score = record.score ?? record.retrieval_score ?? "—";
    return { id, page, route: String(route), score, raw: record };
  }

  async function renderRetrieval() {
    const payload = await loadArtifact("question_traces"); const records=payload.records||[];
    $("#view-root").innerHTML=`<section class="panel" style="margin-bottom:16px"><label class="control">Question<select id="question-select">${records.map((r,i)=>`<option value="${i}">${i+1}. ${escapeHtml(r.question)}</option>`).join("")}</select></label></section><section id="question-summary"></section>`;
    const show=(index)=>{const q=records[Number(index)]||records[0]; if(!q){$("#question-summary").innerHTML='<div class="notice error">No saved question traces were exported.</div>';return;} const baseSteps=[
      ["Read and normalize", `Question: ${q.question}`],
      ["Extract exact clues", `Identifiers: ${(q.exact_identifiers||[]).join(", ")||"none"}`],
      ["Choose route", pretty(q.route||"route stored in raw trace")],
      ["Vector guidance", `${(q.vector_candidates||[]).length} saved candidates`],
      ["Search source-traced records", `${(q.evidence||[]).length} evidence records kept`],
      ["Build evidence envelope", "Direct evidence, vector guidance, contradictions, and source permissions are separated"],
      ["Gemma answer-writing call", `${q.model||"gemma4:26b"} · status ${q.gemma_status||"stored in trace"}`],
      ["Validate and release", `Decision: ${pretty(q.final_release_decision||"stored in trace")}`],
    ]; const evidence=(q.evidence||[]).map(normalizedEvidence); $("#question-summary").innerHTML=`
      <div class="grid cols-2"><section class="panel"><h2>Deterministic and model steps</h2><div class="trace">${baseSteps.map(([title,body],i)=>`<div class="trace-step"><div class="n">${i+1}</div><div class="body"><strong>${escapeHtml(title)}</strong><div class="muted" style="margin-top:4px">${escapeHtml(body)}</div></div></div>`).join("")}</div></section><section class="panel"><h2>Evidence envelope</h2><div class="check-list">${evidence.map(e=>`<div class="check"><span><strong>${escapeHtml(e.id)}</strong><br>${escapeHtml(e.page)} · ${routePill(e.route)}</span><span>score ${escapeHtml(e.score)}</span></div>`).join("")||'<div class="notice">The raw question artifact did not expose a normalized evidence list. Open the raw trace below.</div>'}</div></section></div>
      <section class="panel" style="margin-top:16px"><h2>Final answer</h2><div class="notice">${escapeHtml(q.answer||"No answer text found in normalized fields.")}</div></section>
      <section class="panel" style="margin-top:16px"><h2>Raw saved trace</h2><pre>${escapeHtml(JSON.stringify(q.raw,null,2))}</pre></section>`;}; $("#question-select").addEventListener("change",()=>show($("#question-select").value)); show(0);
  }

  function collectValidationChecks(q) {
    const checks=[]; const raw=q.validation||{};
    if (raw && typeof raw === "object") Object.entries(raw).forEach(([k,v])=>{if(typeof v!=="object")checks.push([k,v]);});
    const rawText=JSON.stringify(q.raw||{});
    const known=["empty_answer_check","unsupported_identifiers","invalid_citation_labels","source_truth_mutation_allowed","final_release_decision"];
    known.forEach((key)=>{ if(!checks.some(([k])=>k===key)){ const match=rawText.match(new RegExp(`"${key}"\\s*:\\s*("[^"]*"|true|false|null|[-0-9.]+)`)); if(match)checks.push([key,JSON.parse(match[1])]); }});
    return checks;
  }

  async function renderValidation() {
    const payload=await loadArtifact("question_traces"); const records=payload.records||[];
    $("#view-root").innerHTML=`<section class="panel" style="margin-bottom:16px"><label class="control">Question<select id="validation-select">${records.map((r,i)=>`<option value="${i}">${i+1}. ${escapeHtml(r.question)}</option>`).join("")}</select></label></section><section id="validation-root"></section>`;
    const show=(i)=>{const q=records[Number(i)]||records[0]; if(!q){$("#validation-root").innerHTML='<div class="notice error">No question traces available.</div>';return;} const checks=collectValidationChecks(q); const answer=String(q.answer||""); const abstain=/does not contain|not found|insufficient|cannot determine|does not specify/i.test(answer); $("#validation-root").innerHTML=`<div class="grid cols-2"><section class="panel"><h2>Validation checks</h2><div class="check-list">${checks.map(([k,v])=>{const pass=!(v===false||String(v).toUpperCase().includes("FAIL")); return `<div class="check"><span>${escapeHtml(k.replaceAll("_"," "))}</span><span class="state ${pass?"pass":"fail"}">${escapeHtml(pretty(v))}</span></div>`;}).join("")||'<div class="notice">Open the raw trace in Retrieval Trace to inspect nested validation fields.</div>'}</div></section><section class="panel"><h2>Release outcome</h2>${metric("Gemma status",q.gemma_status||"—")}${metric("Release decision",q.final_release_decision||"—")}${metric("Answer mode",abstain?"SAFE ABSTENTION":"EVIDENCE-SUPPORTED ANSWER")}<div class="notice" style="margin-top:14px">${escapeHtml(answer||"No normalized answer text found.")}</div></section></div><section class="panel" style="margin-top:16px"><h2>Safety contract</h2><div class="flow"><div class="flow-node"><div class="k">Generated answer</div><div class="v">Gemma writes from approved evidence</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Identifier check</div><div class="v">Unsupported IDs rejected</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Citation check</div><div class="v">Unknown labels rejected</div></div><div class="flow-arrow">→</div><div class="flow-node"><div class="k">Critic decision</div><div class="v">Release or safe abstention</div></div></div></section>`;}; $("#validation-select").addEventListener("change",()=>show($("#validation-select").value));show(0);
  }

  async function renderCurrentView() {
    const handlers = { index: renderIndex, source: renderSource, ocr: renderOcr, classification: renderClassification, graph: renderGraph, vector: renderVector, engram: renderEngram, storage: renderStorage, retrieval: renderRetrieval, validation: renderValidation };
    const handler = handlers[view] || renderIndex;
    await handler();
  }

  async function init() {
    setPageTitle(); renderShell();
    try {
      state.catalog = await fetchJson("data/catalog.json");
      if (!state.catalog.datasets?.length) throw new Error("No datasets are registered. Run the Visual Lab exporter first.");
      const slug = getDatasetSlug();
      state.dataset = state.catalog.datasets.find((item) => item.slug === slug) || state.catalog.datasets[0];
      state.manifest = await fetchJson(state.dataset.manifest);
      renderDatasetControls(); renderStatusStrip(); await renderCurrentView();
    } catch (error) {
      $("#view-root").innerHTML = `<div class="notice error"><strong>Visual Lab could not load.</strong><br>${escapeHtml(error.message)}<br><br>Serve this folder with <code>python -m http.server 8765</code>; do not open the HTML as a file.</div>`;
    }
  }

  init();
})();
