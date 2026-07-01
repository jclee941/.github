<style>
  :root {
    --surface-primary: #08090a;
    --surface-secondary: #0f1011;
    --surface-elevated: #191a1b;
    --text-primary: #f7f8f8;
    --text-secondary: #d0d6e0;
    --text-tertiary: #8a8f98;
    --border-default: rgba(255,255,255,0.08);
    --border-subtle: rgba(255,255,255,0.05);
    --accent-primary: #7170ff;
    --accent-hover: #828fff;
    --status-success: #27a644;
    --status-warning: #d99a2b;
    --status-error: #f05252;
    --status-info: #6ea8fe;
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --space-8: 32px;
    --space-10: 40px;
    --space-12: 48px;
  }

  body {
    max-width: none !important;
    margin: 0 !important;
    padding: 0 !important;
    background:
      radial-gradient(circle at 20% 8%, rgba(113, 112, 255, 0.18), transparent 32rem),
      linear-gradient(180deg, #08090a 0%, #0f1011 58%, #08090a 100%);
    color: var(--text-primary) !important;
    font-family: Inter Variable, SF Pro Display, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif !important;
  }

  body > nav {
    max-width: 1180px;
    margin: var(--space-6) auto 0;
    padding: 0 var(--space-6);
  }

  body > nav a {
    color: var(--text-secondary);
  }

  .elk-demo-shell {
    max-width: 1180px;
    margin: 0 auto;
    padding: var(--space-10) var(--space-6) var(--space-12);
  }

  .elk-demo-hero {
    display: grid;
    grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
    gap: var(--space-8);
    align-items: stretch;
    min-height: 420px;
  }

  .elk-demo-copy {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-5);
  }

  .elk-demo-kicker {
    color: var(--accent-hover);
    font: 510 12px/1.4 Berkeley Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    text-transform: uppercase;
  }

  .elk-demo-copy h1 {
    margin: 0;
    max-width: 720px;
    color: var(--text-primary);
    font-size: clamp(2.2rem, 6vw, 4.2rem);
    line-height: 1.08;
    letter-spacing: 0;
  }

  .elk-title-line {
    display: block;
    white-space: nowrap;
  }

  .elk-demo-copy p {
    max-width: 66ch;
    margin: 0;
    color: var(--text-secondary);
    font-size: 1.06rem;
    line-height: 1.7;
  }

  .elk-copy-line {
    display: block;
  }

  .elk-demo-shell code {
    border: 1px solid var(--border-subtle);
    background: rgba(255,255,255,0.06);
    color: var(--text-primary);
  }

  .elk-evidence-rail {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border-default);
    border-radius: 12px;
    background:
      linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02)),
      var(--surface-secondary);
    box-shadow: 0 16px 60px rgba(113,112,255,0.14);
  }

  .elk-evidence-rail::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    background: linear-gradient(180deg, var(--accent-hover), var(--status-success), var(--status-info));
  }

  .elk-rail-inner {
    display: grid;
    gap: var(--space-4);
    padding: var(--space-6);
  }

  .elk-log-row {
    display: grid;
    grid-template-columns: 86px 1fr auto;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-3);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    background: rgba(255,255,255,0.025);
    color: var(--text-secondary);
    font: 400 13px/1.5 Berkeley Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  .elk-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--status-success);
    box-shadow: 0 0 18px rgba(39,166,68,0.55);
  }

  .elk-demo-grid {
    display: grid;
    grid-template-columns: minmax(300px, 0.85fr) minmax(0, 1.15fr);
    gap: var(--space-8);
    margin-top: var(--space-10);
  }

  .elk-panel,
  .elk-output {
    border: 1px solid var(--border-default);
    border-radius: 12px;
    background: rgba(15,16,17,0.82);
  }

  .elk-panel {
    padding: var(--space-6);
  }

  .elk-panel h2,
  .elk-output h2 {
    margin: 0 0 var(--space-4);
    color: var(--text-primary);
    font-size: 1.35rem;
    letter-spacing: 0;
  }

  .elk-form {
    display: grid;
    gap: var(--space-4);
  }

  .elk-field {
    display: grid;
    gap: var(--space-2);
  }

  .elk-field label {
    color: var(--text-secondary);
    font-size: 0.88rem;
    font-weight: 590;
  }

  .elk-field input,
  .elk-field textarea {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid var(--border-default);
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    color: var(--text-primary);
    padding: var(--space-3);
    font: 400 0.92rem/1.5 Berkeley Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  .elk-field textarea {
    min-height: 150px;
    resize: vertical;
  }

  .elk-field input:focus,
  .elk-field textarea:focus,
  .elk-actions button:focus {
    outline: 2px solid var(--accent-primary);
    outline-offset: 2px;
  }

  .elk-help {
    margin: 0;
    color: var(--text-tertiary);
    font-size: 0.86rem;
    line-height: 1.55;
  }

  .elk-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .elk-actions button {
    min-height: 42px;
    border: 1px solid var(--border-default);
    border-radius: 8px;
    padding: var(--space-3) var(--space-4);
    color: var(--text-primary);
    background: rgba(255,255,255,0.04);
    font-weight: 590;
    cursor: pointer;
    transition: transform 140ms ease-out, background 140ms ease-out, border-color 140ms ease-out;
  }

  .elk-actions button:first-child {
    border-color: rgba(113,112,255,0.6);
    background: var(--accent-hover);
    color: #08090a;
  }

  .elk-actions button:hover {
    transform: translateY(-1px);
    border-color: rgba(255,255,255,0.18);
    background: rgba(130,143,255,0.2);
  }

  .elk-output {
    min-height: 520px;
    overflow: hidden;
  }

  .elk-output-head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: center;
    padding: var(--space-6) var(--space-6) 0;
  }

  .elk-status-pill {
    border: 1px solid var(--border-default);
    border-radius: 999px;
    padding: var(--space-2) var(--space-3);
    color: var(--text-secondary);
    background: rgba(255,255,255,0.035);
    font: 510 12px/1.4 Berkeley Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  .elk-cards {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
    padding: var(--space-6);
  }

  .elk-card {
    min-height: 112px;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: var(--space-4);
    background: rgba(255,255,255,0.025);
  }

  .elk-card strong {
    display: block;
    color: var(--text-primary);
    font-size: 1.35rem;
    line-height: 1.25;
  }

  .elk-card span {
    color: var(--text-tertiary);
    font-size: 0.82rem;
  }

  .elk-json {
    margin: 0 var(--space-6) var(--space-6);
    max-height: 260px;
    overflow: auto;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    background: #08090a;
    color: var(--text-secondary);
    padding: var(--space-4);
    font: 400 13px/1.55 Berkeley Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  .elk-command {
    margin-top: var(--space-8);
    border: 1px solid var(--border-default);
    border-radius: 12px;
    background: rgba(8,9,10,0.72);
    padding: var(--space-6);
  }

  .elk-command pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    background: transparent !important;
    color: var(--text-secondary);
  }

  .elk-command code {
    border: 0;
    background: transparent;
    color: var(--text-secondary);
    padding: 0;
  }

  @media (max-width: 860px) {
    .elk-demo-hero,
    .elk-demo-grid {
      grid-template-columns: 1fr;
    }

    .elk-log-row,
    .elk-cards {
      grid-template-columns: 1fr;
    }

    .elk-output-head {
      align-items: flex-start;
      flex-direction: column;
    }

    .elk-demo-copy h1 {
      font-size: clamp(2.05rem, 10vw, 2.55rem);
    }

    .elk-demo-copy p {
      font-size: 0.98rem;
    }

    .elk-copy-line {
      white-space: nowrap;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .elk-actions button {
      transition: none;
    }

    .elk-actions button:hover {
      transform: none;
    }
  }
</style>

<main class="elk-demo-shell" data-page-title="ELK Evidence Demo">
  <section class="elk-demo-hero" aria-labelledby="elkDemoTitle">
    <div class="elk-demo-copy">
      <div class="elk-demo-kicker">jclee-bot / native health / ELK</div>
      <h1 id="elkDemoTitle" aria-label="ELK 근거를 데모로 검증합니다">
        <span class="elk-title-line">ELK 근거를</span>
        <span class="elk-title-line">데모로 검증합니다.</span>
      </h1>
      <p>
        <span class="elk-copy-line">ELK 자격 증명은 브라우저에</span>
        <span class="elk-copy-line">노출하지 않습니다.</span>
        <span class="elk-copy-line">토큰은 <code>NATIVE_HEALTH_TOKEN</code>으로</span>
        <span class="elk-copy-line"><code>/api/v1/native_health</code>에만 전송됩니다.</span>
        <span class="elk-copy-line">App 서버가 ELK에 질의하고</span>
        <span class="elk-copy-line">결과 카드만 렌더링합니다.</span>
      </p>
    </div>
    <aside class="elk-evidence-rail" aria-label="ELK evidence pipeline">
      <div class="elk-rail-inner">
        <div class="elk-log-row"><span>source</span><span>jclee-bot-app Docker JSON logs</span><i class="elk-dot"></i></div>
        <div class="elk-log-row"><span>shipper</span><span>Filebeat decodes JSON and adds Docker metadata</span><i class="elk-dot"></i></div>
        <div class="elk-log-row"><span>index</span><span>jclee-bot-logs-* on &lt;homelab-elk&gt;</span><i class="elk-dot"></i></div>
        <div class="elk-log-row"><span>proof</span><span>native_health checks cluster and index presence</span><i class="elk-dot"></i></div>
      </div>
    </aside>
  </section>

  <section class="elk-demo-grid" aria-label="ELK evidence controls and output">
    <div class="elk-panel">
      <h2>Live check</h2>
      <form class="elk-form" id="elkEvidenceForm">
        <div class="elk-field">
          <label for="elkNativeHealthEndpoint">Native health endpoint</label>
          <input id="elkNativeHealthEndpoint" name="endpoint" value="https://bot.jclee.me/api/v1/native_health" autocomplete="off" readonly>
          <p class="elk-help">Same-origin deployments can use <code>/api/v1/native_health</code>. GitHub Pages users can run the curl command below if CORS blocks browser fetch.</p>
        </div>
        <div class="elk-field">
          <label for="elkRepository">Repository</label>
          <input id="elkRepository" name="repository" value="jclee941/jclee-bot" autocomplete="off">
        </div>
        <div class="elk-field">
          <label for="elkToken">NATIVE_HEALTH_TOKEN</label>
          <input id="elkToken" name="token" type="password" placeholder="Paste token for this browser session only" autocomplete="off">
        </div>
        <div class="elk-actions">
          <button type="submit">Run ELK health</button>
          <button type="button" id="elkSampleButton">Load sample</button>
        </div>
      </form>
      <div class="elk-field" style="margin-top: var(--space-6);">
        <label for="elkJsonInput">Paste native-health JSON</label>
        <textarea id="elkJsonInput" placeholder='{"checks":[{"name":"elk_health","status":"healthy","summary":"ELK is reachable and bot log indices are present"}]}'></textarea>
        <div class="elk-actions">
          <button type="button" id="elkRenderJsonButton">Render pasted JSON</button>
        </div>
      </div>
    </div>

    <div class="elk-output" aria-live="polite">
      <div class="elk-output-head">
        <h2>Evidence output</h2>
        <span class="elk-status-pill" id="elkStatusPill">idle</span>
      </div>
      <div class="elk-cards" id="elkEvidenceCards">
        <div class="elk-card"><span>Status</span><strong>Waiting</strong></div>
        <div class="elk-card"><span>Check</span><strong>elk_health</strong></div>
        <div class="elk-card"><span>Index namespace</span><strong>jclee-bot-logs-*</strong></div>
        <div class="elk-card"><span>ELK host</span><strong>&lt;homelab-elk&gt;</strong></div>
      </div>
      <pre class="elk-json" id="elkJsonOutput">Run a check or load the sample response.</pre>
    </div>
  </section>

  <section class="elk-command" aria-labelledby="elkCurlTitle">
    <h2 id="elkCurlTitle">CLI evidence path</h2>
    <pre><code>curl -fsS --retry 3 --retry-delay 5 --max-time 180 \
  -X POST "https://bot.jclee.me/api/v1/native_health" \
  -H "Authorization: Bearer ${NATIVE_HEALTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"repository":"jclee941/jclee-bot","dry_run":true,"checks":["elk_health"]}'</code></pre>
  </section>
</main>

<script>
  const sampleResponse = {
    dry_run: true,
    repository: "jclee941/jclee-bot",
    checks: [
      {
        name: "elk_health",
        status: "healthy",
        summary: "ELK is reachable and bot log indices are present"
      }
    ],
    actions: ["close_matching_issues"],
    details: {
      cluster_status: "green",
      jclee_bot_indices: "1",
      legacy_indices: "0",
      index_pattern: "jclee-bot-logs-*",
      elk_host: "<homelab-elk>"
    }
  };

  const form = document.getElementById("elkEvidenceForm");
  const statusPill = document.getElementById("elkStatusPill");
  const cards = document.getElementById("elkEvidenceCards");
  const output = document.getElementById("elkJsonOutput");
  const endpointInput = document.getElementById("elkNativeHealthEndpoint");
  const repoInput = document.getElementById("elkRepository");
  const tokenInput = document.getElementById("elkToken");
  const jsonInput = document.getElementById("elkJsonInput");
  const allowedNativeHealthEndpoints = new Set([
    "https://bot.jclee.me/api/v1/native_health",
    `${window.location.origin}/api/v1/native_health`
  ]);

  function firstCheck(payload) {
    return Array.isArray(payload.checks) && payload.checks.length > 0 ? payload.checks[0] : {};
  }

  function cardValue(value) {
    return value === undefined || value === null || value === "" ? "not reported" : String(value);
  }

  function replaceCards(items) {
    cards.replaceChildren();
    for (const [label, value] of items) {
      const wrapper = document.createElement("div");
      const labelNode = document.createElement("span");
      const valueNode = document.createElement("strong");
      wrapper.className = "elk-card";
      labelNode.textContent = label;
      valueNode.textContent = cardValue(value);
      wrapper.append(labelNode, valueNode);
      cards.append(wrapper);
    }
  }

  function renderEvidence(payload) {
    const check = firstCheck(payload);
    const details = payload.details || {};
    const status = check.status || "unknown";
    statusPill.textContent = status;
    replaceCards([
      ["Status", status],
      ["Summary", check.summary || "No summary"],
      ["Repository", payload.repository || "jclee941/jclee-bot"],
      ["Check", check.name || "elk_health"],
      ["Cluster", details.cluster_status || "returned by native health"],
      ["Index pattern", details.index_pattern || "jclee-bot-logs-*"],
      ["jclee-bot indices", details.jclee_bot_indices || "reported by ELK"],
      ["Legacy indices", details.legacy_indices || "compatibility only"]
    ]);
    output.textContent = JSON.stringify(payload, null, 2);
  }

  function renderError(message) {
    statusPill.textContent = "error";
    replaceCards([
      ["Status", "error"],
      ["Cause", message],
      ["Fallback", "Use CLI evidence path"],
      ["Endpoint", endpointInput.value]
    ]);
    output.textContent = message;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    statusPill.textContent = "loading";
    const endpoint = endpointInput.value.trim();
    const token = tokenInput.value.trim();
    const payload = { repository: repoInput.value.trim(), dry_run: true, checks: ["elk_health"] };
    if (!endpoint || !token) {
      renderError("Endpoint and NATIVE_HEALTH_TOKEN are required for a live browser check.");
      return;
    }
    if (!allowedNativeHealthEndpoints.has(endpoint)) {
      renderError("Blocked unsafe endpoint. NATIVE_HEALTH_TOKEN can only be sent to the jclee-bot native health endpoint.");
      return;
    }
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      const body = await response.json();
      if (!response.ok) {
        renderError(`HTTP ${response.status}: ${JSON.stringify(body)}`);
        return;
      }
      renderEvidence(body);
    } catch (error) {
      renderError(`Browser fetch failed: ${error.message}. If this page is served from GitHub Pages, use the CLI evidence path or paste the JSON response.`);
    }
  });

  document.getElementById("elkSampleButton").addEventListener("click", () => {
    renderEvidence(sampleResponse);
  });

  document.getElementById("elkRenderJsonButton").addEventListener("click", () => {
    try {
      renderEvidence(JSON.parse(jsonInput.value));
    } catch (error) {
      renderError(`Invalid JSON: ${error.message}`);
    }
  });
</script>
