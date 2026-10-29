const EVIDENCE_PAGE_SIZE = 100;
const GOOGLE_MEET_URL = /^https?:\/\/meet\.google\.com\/(?:meet\/)?[a-z]{3}-[a-z]{4}-[a-z]{3}(?:[/?#].*)?$/i;
const OPERATOR_SETUP_COMMAND = "cd source && ./scripts/runtime-settings.sh wizard";
const OPERATOR_APPLY_COMMAND = "cd source && ./scripts/runtime-settings.sh apply";
const OPERATOR_VEXA_VERIFY_COMMAND = "cd source && ./scripts/vexa-selfhost.sh verify";
const OPERATOR_VEXA_MINT_COMMAND = "cd source && ./scripts/vexa-selfhost.sh mint-token";
const OPERATOR_VERIFY_COMMAND = "cd source && ./scripts/verify.sh";
const OPERATOR_RUNBOOK = `cd source
# 1) Nếu API key từng lộ trong chat/editor: mint replacement key ở terminal.
./scripts/vexa-selfhost.sh mint-token
# 2) Dán key mới vào prompt ẩn, chọn model/threshold.
./scripts/runtime-settings.sh wizard
# 3) Build + recreate backend, worker, dashboard.
./scripts/runtime-settings.sh apply
# 4) Xác minh readiness, sau đó hard refresh dashboard.
./scripts/verify.sh`;
const state = {
  meetingId: null, meeting: null, runId: null, runs: [], stream: null, refreshTimer: null,
  handoffText: "", timeline: [], selectedWindow: null, evidenceRows: [], evidenceOffset: 0, hasMoreEvidence: false,
  operatorSettings: null,
};
const byId = (id) => document.getElementById(id);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const api = (path, options = {}) => fetch(`/api${path}`, {
  ...options,
  headers: { "Content-Type": "application/json", ...options.headers },
});

function setStatus(value, isError = false) {
  const element = byId("status");
  element.textContent = value;
  element.classList.toggle("is-error", isError);
}
function ratio(value) { return `${Math.round((value || 0) * 100)}%`; }
function score(value) { return value == null ? "Không đủ dữ liệu" : Number(value).toFixed(2); }
function date(value) { return value ? new Date(value).toLocaleString("vi-VN") : "—"; }
function time(value) { return value ? new Date(value).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : "—"; }
function runQuery() { return state.runId ? `?run_id=${encodeURIComponent(state.runId)}` : ""; }
function labelText(label) {
  return ({ positive: "Tích cực", neutral: "Trung tính", negative: "Tiêu cực", unknown: "Unknown" })[label] || "Chưa dự đoán";
}

async function json(path, options) {
  const response = await api(path, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? `: ${body.detail}` : "";
    throw new Error(`API ${response.status}${detail}`);
  }
  return body;
}

function setStartMeetingStatus(message = "", isError = false) {
  const element = byId("start-meeting-status");
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function setOperatorStatus(message = "", isError = false) {
  const element = byId("operator-status");
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function setLocalSetupStatus(message = "", isError = false) {
  const element = byId("local-setup-status");
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function updateArtifactFields() {
  const tfidf = byId("setup-adapter").value === "tfidf-logreg";
  byId("setup-artifact-fields").hidden = !tfidf;
  byId("setup-artifact-dir").required = tfidf;
  byId("setup-artifact-sha256").required = tfidf;
}

function updateLocalSetupButton() {
  const enabled = byId("setup-confirm").checked && Boolean(byId("setup-model-version").value.trim())
    && Boolean(byId("setup-preprocessing-version").value.trim()) && byId("local-setup-form").dataset.enabled === "true";
  byId("submit-local-setup").disabled = !enabled;
}

function renderLocalSetupForm(payload) {
  state.operatorSettings = payload;
  const enabled = Boolean(payload.security?.dashboard_submit_available);
  const form = byId("local-setup-form");
  form.dataset.enabled = String(enabled);
  form.hidden = !enabled;
  if (!enabled) return;
  const model = payload.model || {};
  byId("setup-vexa-key").value = "";
  byId("setup-adapter").value = model.classifier_adapter || "rules";
  byId("setup-model-version").value = model.model_version || "";
  byId("setup-preprocessing-version").value = model.preprocessing_version || "";
  byId("setup-threshold").value = model.sentiment_confidence_threshold ?? 0.6;
  byId("setup-artifact-dir").value = "";
  byId("setup-artifact-sha256").value = "";
  byId("setup-confirm").checked = false;
  updateArtifactFields();
  updateLocalSetupButton();
  setLocalSetupStatus("");
}

function integrationStatusText(status) {
  return ({
    configured: "Đã cấu hình",
    needs_secret: "Cần secret cục bộ",
    needs_configuration: "Cần cấu hình",
    not_required: "Không yêu cầu",
  })[status] || "Chưa rõ";
}

function appendIntegrationDetail(container, label, value) {
  const item = document.createElement("li");
  const rendered = typeof value === "boolean" ? (value ? "đã cấu hình" : "chưa cấu hình") : String(value);
  item.textContent = `${label}: ${rendered}`;
  container.append(item);
}

function integrationById(payload, id) {
  return (payload.integrations || []).find((integration) => integration.id === id) || {};
}

function setupState(status) {
  return status === "configured" || status === "not_required" ? "ready" : "needs_action";
}

function addSetupStep(container, { number, title, description, command, state = "action", buttonLabel = "Sao chép lệnh" }) {
  const item = document.createElement("li");
  item.className = `setup-step setup-${state}`;
  const numberNode = document.createElement("span");
  numberNode.className = "setup-number";
  numberNode.textContent = String(number);
  const body = document.createElement("div");
  const heading = document.createElement("h4");
  heading.textContent = title;
  const status = document.createElement("span");
  status.className = `setup-state setup-state-${state}`;
  status.textContent = ({ ready: "Sẵn sàng", needs_action: "Cần thực hiện", action: "Thao tác cục bộ" })[state];
  const copy = document.createElement("p");
  copy.textContent = description;
  const commandNode = document.createElement("code");
  commandNode.textContent = command;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button-secondary setup-copy";
  button.textContent = buttonLabel;
  button.addEventListener("click", () => copyOperatorCommand(command, `Đã sao chép lệnh cho bước ${number}. Chạy trong terminal cục bộ.`));
  body.append(heading, status, copy, commandNode, button);
  item.append(numberNode, body);
  container.append(item);
}

function renderOperatorSetup(payload) {
  const vexa = integrationById(payload, "vexa");
  const transcription = integrationById(payload, "transcription");
  const model = payload.model || {};
  const modelState = model.artifact_required && !model.artifact_configured ? "needs_action" : "ready";
  const steps = byId("operator-setup-steps");
  steps.replaceChildren();
  addSetupStep(steps, {
    number: 1,
    title: "Kiểm tra Vexa runner",
    description: "Kiểm tra gateway và image bot trước khi tạo meeting. Lệnh không in API key.",
    command: OPERATOR_VEXA_VERIFY_COMMAND,
  });
  addSetupStep(steps, {
    number: 2,
    title: "Cấp hoặc rotate Vexa API key",
    description: vexa.status === "configured"
      ? "Key đang được cấu hình. Nếu key từng xuất hiện trong chat/editor, mint key thay thế ngay; token chỉ hiện một lần trong terminal."
      : "Chưa có key hợp lệ. Mint key có scope bot/transcript rồi chuyển sang bước 3 để lưu kín.",
    command: OPERATOR_VEXA_MINT_COMMAND,
    state: vexa.status === "configured" ? "action" : "needs_action",
    buttonLabel: "Sao chép lệnh mint",
  });
  addSetupStep(steps, {
    number: 3,
    title: "Lưu cấu hình Vexa và model",
    description: `Wizard che input API key, sau đó cấu hình ${model.classifier_adapter || "model"}, version ${model.model_version || "—"} và confidence threshold.`,
    command: OPERATOR_SETUP_COMMAND,
    state: modelState,
    buttonLabel: "Sao chép lệnh wizard",
  });
  addSetupStep(steps, {
    number: 4,
    title: "Build và recreate service",
    description: "Áp dụng settings.env bằng cách build lại và tạo lại backend, worker, dashboard. PostgreSQL và Valkey không bị xóa.",
    command: OPERATOR_APPLY_COMMAND,
  });
  addSetupStep(steps, {
    number: 5,
    title: "Xác minh và mở dashboard",
    description: transcription.status === "configured"
      ? "Transcription đã có cấu hình. Chạy readiness, rồi hard refresh dashboard để xem trạng thái mới."
      : "Sau readiness, hoàn tất transcription trước khi yêu cầu bot tạo transcript thật.",
    command: OPERATOR_VERIFY_COMMAND,
    state: setupState(transcription.status),
    buttonLabel: "Sao chép lệnh verify",
  });
}

function renderOperatorSettings(payload) {
  renderLocalSetupForm(payload);
  const model = payload.model || {};
  const analysis = payload.analysis || {};
  const summary = byId("operator-summary");
  summary.replaceChildren(
    card("Model đang dùng", model.model_version || "—", `${model.classifier_adapter || "—"} · preprocessing ${model.preprocessing_version || "—"}`),
    card("Confidence threshold", ratio(model.sentiment_confidence_threshold), model.artifact_required ? "Artifact có kiểm chứng là bắt buộc" : "Rules baseline không cần artifact"),
    card("Polling transcript", `${analysis.poll_interval_seconds ?? "—"} giây`, `Debounce ${analysis.debounce_seconds ?? "—"} giây · retry ${analysis.max_retries ?? "—"}`),
  );
  const integrations = byId("operator-integrations");
  integrations.replaceChildren();
  (payload.integrations || []).forEach((integration) => {
    const item = document.createElement("article");
    item.className = "operator-integration";
    const heading = document.createElement("h4");
    heading.textContent = integration.label || integration.id;
    const status = document.createElement("p");
    status.className = `integration-status integration-${integration.status || "unknown"}`;
    status.textContent = integrationStatusText(integration.status);
    const details = document.createElement("ul");
    Object.entries(integration.configuration || {}).forEach(([key, value]) => {
      appendIntegrationDetail(details, key.replaceAll("_", " "), value);
    });
    item.append(heading, status, details);
    if (integration.secret_fields?.length) {
      const note = document.createElement("p");
      note.className = "integration-note";
      note.textContent = `Secret chỉ nhập trong terminal: ${integration.secret_fields.join(", ")}.`;
      item.append(note);
    }
    integrations.append(item);
  });
  renderOperatorSetup(payload);
  const services = (payload.restart?.recreate_services || []).join(", ");
  setOperatorStatus(services ? `Thay đổi cấu hình sẽ build và tạo lại: ${services}.` : "Đã tải trạng thái cấu hình.");
}

async function loadOperatorSettings() {
  setOperatorStatus("Đang kiểm tra cấu hình vận hành…");
  renderOperatorSettings(await json("/v1/operator/settings"));
}

async function copyOperatorCommand(command, successMessage) {
  const feedback = byId("operator-copy-status");
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard API is unavailable");
    await navigator.clipboard.writeText(command);
    feedback.textContent = successMessage;
  } catch (_) {
    feedback.textContent = "Không thể sao chép tự động. Hãy sao chép lệnh hiển thị bên dưới.";
  }
}

function updateStartMeetingButton() {
  const validUrl = GOOGLE_MEET_URL.test(byId("meet-url").value.trim());
  byId("start-meeting").disabled = !(validUrl && byId("meeting-consent").checked);
}

function renderActiveMeeting() {
  const element = byId("active-meeting");
  if (!state.meeting) { element.hidden = true; return; }
  element.textContent = `Meeting ${state.meetingId} · ${state.meeting.status}`;
  element.hidden = false;
}

function renderLastUpdated() {
  const element = byId("last-updated");
  element.textContent = state.meetingId ? `Dữ liệu tải lần cuối: ${date(new Date())}` : "";
}

function renderRunSelector(runs) {
  const select = byId("run-select");
  select.replaceChildren();
  if (!runs.length) {
    const option = new Option("Chưa có analysis run", "");
    select.add(option);
    select.disabled = true;
    state.runId = null;
    return;
  }
  if (!runs.some((run) => run.id === state.runId)) state.runId = runs[0].id;
  runs.forEach((run) => {
    const option = new Option(`${run.model_version} · rev ${run.source_revision} · ${run.kind} · ${run.status}`, run.id);
    option.selected = run.id === state.runId;
    select.add(option);
  });
  select.disabled = false;
}

function card(name, value, detail, tone = "") {
  const node = byId("metric-card").content.cloneNode(true);
  const article = node.querySelector("article");
  article.classList.toggle(`tone-${tone}`, Boolean(tone));
  node.querySelector(".card-label").textContent = name;
  node.querySelector("strong").textContent = value;
  node.querySelector("small").textContent = detail;
  return node;
}

function renderOverview(overview) {
  const metrics = overview.metrics || {};
  const total = metrics.unit_count || 0;
  const accepted = metrics.accepted_unit_count || 0;
  const predicted = metrics.predicted_unit_count || 0;
  const container = byId("metrics");
  container.replaceChildren(
    card("Tích cực", ratio(overview.ratios?.positive), "trên output có nhãn", "positive"),
    card("Trung tính", ratio(overview.ratios?.neutral), "trên output có nhãn", "neutral"),
    card("Tiêu cực", ratio(overview.ratios?.negative), "trên output có nhãn", "negative"),
    card("Prediction coverage", ratio(metrics.prediction_coverage), `${predicted}/${accepted} unit đạt ngưỡng`),
    card("Effective coverage", ratio(metrics.effective_coverage), `${predicted}/${total} unit đầu vào`),
    card("Polarity", score(overview.score), "P(positive) − P(negative)"),
    card("Batch inference", `${metrics.inference_total_ms ?? "—"} ms`, "một lần chạy; không phải P95"),
  );
  byId("run-meta").textContent = overview.run_id
    ? `${overview.model_version} · preprocessing ${overview.preprocessing_version} · revision ${overview.source_revision}`
    : "Chưa có analysis run";
  byId("coverage-note").textContent = total
    ? `${total - accepted} unit bị quality gate loại; unknown và coverage thấp không được gộp vào neutral.`
    : "Chưa có unit final đủ điều kiện để tổng hợp.";
  byId("overview-section").hidden = false;
}

function renderHandoffSummary(overview) {
  const metrics = overview.metrics || {};
  const total = metrics.unit_count || 0;
  const accepted = metrics.accepted_unit_count || 0;
  const predicted = metrics.predicted_unit_count || 0;
  const timestamp = new Date().toLocaleString("vi-VN");
  const text = [
    "MEETING INTELLIGENCE — TÓM TẮT BÀN GIAO (ĐÃ LƯỢC BỎ TRANSCRIPT)",
    `Tạo lúc: ${timestamp}`,
    `Application meeting UUID: ${state.meetingId}`,
    `Trạng thái meeting: ${state.meeting?.status || "—"}`,
    `Analysis run ID: ${overview.run_id || "chưa có"}`,
    `Trạng thái run: ${overview.status || "not_requested"}`,
    `Model/adapter version: ${overview.model_version || "—"}`,
    `Preprocessing version: ${overview.preprocessing_version || "—"}`,
    `Transcript revision: ${overview.source_revision ?? "—"}`,
    `Unit: ${predicted}/${accepted}/${total} (predicted/accepted/total)`,
    `Prediction coverage: ${ratio(metrics.prediction_coverage)}`,
    `Effective coverage: ${ratio(metrics.effective_coverage)}`,
    `Batch inference: ${metrics.inference_total_ms ?? "—"} ms`,
    "Phạm vi: trạng thái vận hành của một run; không phải accuracy, P95, hay đánh giá con người.",
    "Dữ liệu bị loại: transcript, evidence nguyên văn, tên người nói và secret.",
  ].join("\n");
  state.handoffText = text;
  byId("handoff-preview").textContent = text;
  byId("handoff-summary").hidden = false;
}

function renderComparison(runs) {
  const body = byId("comparison-body");
  body.replaceChildren();
  runs.forEach((run) => {
    const metrics = run.metrics || {};
    const row = document.createElement("tr");
    const values = [
      `${run.model_version} (${run.kind})`, `rev ${run.source_revision}`, run.status,
      `${metrics.predicted_unit_count ?? 0}/${metrics.accepted_unit_count ?? 0}`,
      ratio(metrics.effective_coverage),
      metrics.inference_total_ms == null ? "—" : `${metrics.inference_total_ms} ms`,
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index === 2) cell.className = `run-status run-${run.status}`;
      row.append(cell);
    });
    body.append(row);
  });
  byId("comparison-section").hidden = !runs.length;
}

function renderTranscript(rows) {
  const container = byId("transcript");
  container.replaceChildren();
  byId("transcript-meta").textContent = `${rows.length} segment · tự cập nhật khi transcript thay đổi`;
  if (!rows.length) {
    const message = document.createElement("p");
    message.className = "empty-copy";
    message.textContent = "Chưa có transcript final. Hãy admit bot, nói rõ 15–20 giây và chờ STT xử lý.";
    container.append(message);
  } else {
    rows.forEach((row) => {
      const article = document.createElement("article");
      article.className = "transcript-item";
      const meta = document.createElement("small");
      meta.textContent = `${row.speaker || "Chưa gán speaker"} · ${row.is_final ? "final" : "draft"} · ${Number(row.start).toFixed(1)}s`;
      const text = document.createElement("p");
      text.textContent = row.text;
      article.append(meta, text);
      container.append(article);
    });
  }
  byId("transcript-section").hidden = false;
}

function renderSpeakers(rows) {
  const element = byId("speaker-metrics");
  element.replaceChildren();
  if (!rows.length) {
    const message = document.createElement("p");
    message.className = "empty-copy";
    message.textContent = "Run này chưa có transcript final được gán speaker để tổng hợp.";
    element.append(message);
  } else {
    rows.forEach((row) => {
      const cardNode = document.createElement("article");
      cardNode.className = "speaker-card";
      const title = document.createElement("h3");
      title.textContent = row.speaker;
      const meta = document.createElement("p");
      meta.textContent = `${row.unit_count} unit · coverage ${ratio(row.coverage)}`;
      const metrics = document.createElement("p");
      metrics.textContent = `Tích cực ${ratio(row.ratios?.positive)} · Trung tính ${ratio(row.ratios?.neutral)} · Tiêu cực ${ratio(row.ratios?.negative)} · Polarity ${score(row.score)}`;
      cardNode.append(title, meta, metrics);
      element.append(cardNode);
    });
  }
  byId("speaker-section").hidden = false;
}

function renderTimeline(rows) {
  const element = byId("timeline");
  element.replaceChildren();
  if (state.selectedWindow && !rows.some((row) => row.start === state.selectedWindow.start && row.end === state.selectedWindow.end)) {
    state.selectedWindow = null;
  }
  if (!rows.length) {
    const message = document.createElement("p");
    message.className = "empty-copy";
    message.textContent = "Chưa có cửa sổ phân tích cho run này.";
    element.append(message);
  } else {
    rows.forEach((row) => {
      const selected = row.start === state.selectedWindow?.start && row.end === state.selectedWindow?.end;
      const point = document.createElement("button");
      point.type = "button";
      const value = row.score ?? 0;
      point.className = `point ${value > 0.1 ? "positive" : value < -0.1 ? "negative" : "neutral"}`;
      point.classList.toggle("is-selected", selected);
      point.style.setProperty("--point-height", `${Math.max(18, Math.min(100, Math.abs(value) * 100))}%`);
      point.title = `${date(row.start)} · polarity ${score(row.score)} · coverage ${ratio(row.coverage)} · ${row.unit_count} unit`;
      point.setAttribute("aria-pressed", String(selected));
      point.setAttribute("aria-label", `Lọc evidence từ ${time(row.start)} đến ${time(row.end)}; polarity ${score(row.score)}.`);
      point.addEventListener("click", () => {
        state.selectedWindow = selected ? null : { start: row.start, end: row.end };
        renderTimeline(state.timeline);
        loadEvidence().catch(showError);
      });
      const label = document.createElement("span");
      label.textContent = time(row.start);
      point.append(label);
      element.append(point);
    });
  }
  renderTimelineSelection();
  byId("timeline-section").hidden = false;
}

function renderTimelineSelection() {
  const selected = state.selectedWindow;
  byId("timeline-selection").textContent = selected
    ? `Đang chỉ xem evidence thuộc ${time(selected.start)} – ${time(selected.end)}.`
    : "Chọn một cột để chỉ xem evidence thuộc phút đó.";
  byId("clear-window").hidden = !selected;
}

function renderEvidence() {
  const container = byId("evidence");
  container.replaceChildren();
  const rows = state.evidenceRows;
  if (!rows.length) {
    const message = document.createElement("p");
    message.className = "empty-copy";
    message.textContent = "Không có evidence phù hợp bộ lọc trong run này.";
    container.append(message);
  } else {
    const template = byId("evidence-item");
    rows.forEach((row) => {
      const node = template.content.cloneNode(true);
      const label = node.querySelector(".evidence-label");
      label.textContent = labelText(row.label);
      label.classList.add(`label-${row.label}`);
      node.querySelector(".evidence-confidence").textContent = `confidence ${ratio(row.confidence)}`;
      node.querySelector("p").textContent = row.text;
      const reasons = row.quality_reasons?.length ? ` · ${row.quality_reasons.join(", ")}` : "";
      node.querySelector(".evidence-meta").textContent = `${row.speaker || "Chưa gán speaker"} · ${date(row.start)} · ${row.quality_status}${reasons}`;
      container.append(node);
    });
  }
  const selected = state.selectedWindow;
  const scope = selected ? ` trong khoảng ${time(selected.start)} – ${time(selected.end)}` : "";
  byId("evidence-summary").textContent = rows.length
    ? `Đang hiển thị ${rows.length} evidence${scope}. Mỗi lần tải tối đa ${EVIDENCE_PAGE_SIZE} evidence theo bộ lọc.`
    : `Không có evidence${scope} theo bộ lọc hiện tại.`;
  byId("load-more-evidence").hidden = !state.hasMoreEvidence;
  byId("evidence-section").hidden = false;
}

async function loadEvidence({ append = false } = {}) {
  if (!state.meetingId || !state.runId) {
    state.evidenceRows = [];
    state.hasMoreEvidence = false;
    return renderEvidence();
  }
  if (!append) {
    state.evidenceRows = [];
    state.evidenceOffset = 0;
  }
  const params = new URLSearchParams({ run_id: state.runId });
  const label = byId("evidence-label").value;
  const minConfidence = byId("evidence-confidence").value;
  if (label) params.set("label", label);
  if (minConfidence !== "0") params.set("min_confidence", minConfidence);
  if (state.selectedWindow) {
    params.set("window_start", state.selectedWindow.start);
    params.set("window_end", state.selectedWindow.end);
  }
  params.set("limit", EVIDENCE_PAGE_SIZE);
  params.set("offset", state.evidenceOffset);
  const rows = await json(`/v1/meetings/${state.meetingId}/analytics/units?${params}`);
  state.evidenceRows = append ? [...state.evidenceRows, ...rows] : rows;
  state.evidenceOffset = state.evidenceRows.length;
  state.hasMoreEvidence = rows.length === EVIDENCE_PAGE_SIZE;
  renderEvidence();
}

async function refresh() {
  if (!state.meetingId || !UUID.test(state.meetingId)) return;
  const runs = await json(`/v1/meetings/${state.meetingId}/analysis`);
  state.runs = runs;
  renderRunSelector(runs);
  const query = runQuery();
  const [transcript, overview, speakers, timeline] = await Promise.all([
    json(`/v1/meetings/${state.meetingId}/transcript`),
    json(`/v1/meetings/${state.meetingId}/analytics/overview${query}`),
    json(`/v1/meetings/${state.meetingId}/analytics/speakers${query}`),
    json(`/v1/meetings/${state.meetingId}/analytics/timeline${query}`),
  ]);
  state.runId = overview.run_id || state.runId;
  renderTranscript(transcript);
  renderOverview(overview);
  renderHandoffSummary(overview);
  renderComparison(runs);
  renderSpeakers(speakers);
  state.timeline = timeline;
  renderTimeline(state.timeline);
  await loadEvidence();
  byId("empty-state").hidden = Boolean(runs.length);
  renderLastUpdated();
  setStatus(`Transcript ${transcript.length} segment · Run ${overview.status} · revision ${overview.source_revision ?? "—"}`);
}

function scheduleRefresh() {
  clearTimeout(state.refreshTimer);
  state.refreshTimer = setTimeout(() => refresh().catch(showError), 350);
}

function connectEvents() {
  state.stream?.close();
  state.stream = new EventSource(`/api/v1/meetings/${state.meetingId}/events`);
  state.stream.addEventListener("open", () => setStatus("Kết nối cập nhật trực tiếp."));
  state.stream.addEventListener("transcript.segment.upserted", scheduleRefresh);
  state.stream.addEventListener("analysis.sentiment.updated", scheduleRefresh);
  state.stream.addEventListener("analysis.sentiment.failed", scheduleRefresh);
  state.stream.addEventListener("error", () => setStatus("Đang kết nối lại kênh cập nhật trực tiếp…"));
}

function showError(error) { setStatus(`Không tải được dashboard: ${error.message}`, true); }

async function selectMeeting(meeting) {
  if (!meeting?.id || !UUID.test(meeting.id)) throw new Error("Meeting ID không hợp lệ");
  state.meetingId = meeting.id;
  state.meeting = meeting;
  state.runId = null;
  state.handoffText = "";
  state.timeline = [];
  state.selectedWindow = null;
  state.evidenceRows = [];
  state.evidenceOffset = 0;
  state.hasMoreEvidence = false;
  byId("handoff-summary").hidden = true;
  byId("handoff-copy-status").textContent = "";
  byId("refresh-dashboard").disabled = false;
  byId("meeting-id").value = meeting.id;
  renderActiveMeeting();
  await refresh();
  connectEvents();
}

async function loadLatestMeeting() {
  const meetings = await json("/v1/meetings?limit=1");
  if (!meetings.length) {
    byId("empty-state").hidden = false;
    setStatus("Chưa có meeting nào. Dán Google Meet URL ở biểu mẫu phía trên để yêu cầu bot tham gia.");
    return;
  }
  await selectMeeting(meetings[0]);
}

byId("meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = byId("meeting-id").value.trim();
  try { await (id ? selectMeeting(await json(`/v1/meetings/${id}`)) : loadLatestMeeting()); } catch (error) { showError(error); }
});
byId("start-meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const meetingUrl = byId("meet-url").value.trim();
  const botName = byId("bot-name").value.trim() || "Meeting Assistant";
  if (!GOOGLE_MEET_URL.test(meetingUrl)) {
    setStartMeetingStatus("URL không hợp lệ. Dùng https://meet.google.com/abc-defg-hij hoặc dạng /meet/.", true);
    return;
  }
  if (!byId("meeting-consent").checked) {
    setStartMeetingStatus("Hãy xác nhận consent trước khi gửi yêu cầu cho bot.", true);
    return;
  }
  const button = byId("start-meeting");
  button.disabled = true;
  setStartMeetingStatus("Đang gửi yêu cầu để bot tham gia Google Meet…");
  try {
    const meeting = await json("/v1/meetings", {
      method: "POST",
      body: JSON.stringify({ meeting_url: meetingUrl, bot_name: botName }),
    });
    setStartMeetingStatus(`Đã tạo meeting ${meeting.id}. Host hãy duyệt bot; dashboard đang mở meeting này.`);
    byId("meet-url").value = "";
    byId("meeting-consent").checked = false;
    updateStartMeetingButton();
    await selectMeeting(meeting);
  } catch (error) {
    setStartMeetingStatus(`Không thể tạo bot: ${error.message}`, true);
    updateStartMeetingButton();
  }
});
byId("meet-url").addEventListener("input", updateStartMeetingButton);
byId("meeting-consent").addEventListener("change", updateStartMeetingButton);
byId("run-final").addEventListener("click", async () => {
  if (!state.meetingId) return setStatus("Chưa có meeting để phân tích.", true);
  try {
    const run = await json(`/v1/meetings/${state.meetingId}/analysis?kind=final`, { method: "POST" });
    state.runId = run.run_id;
    state.selectedWindow = null;
    await refresh();
  } catch (error) { showError(error); }
});
byId("refresh-dashboard").addEventListener("click", () => refresh().catch(showError));
byId("run-select").addEventListener("change", async (event) => {
  state.runId = event.target.value || null;
  state.selectedWindow = null;
  try { await refresh(); } catch (error) { showError(error); }
});
byId("evidence-label").addEventListener("change", () => loadEvidence().catch(showError));
byId("evidence-confidence").addEventListener("change", () => loadEvidence().catch(showError));
byId("clear-window").addEventListener("click", () => {
  state.selectedWindow = null;
  renderTimeline(state.timeline);
  loadEvidence().catch(showError);
});
byId("load-more-evidence").addEventListener("click", () => loadEvidence({ append: true }).catch(showError));
byId("copy-handoff").addEventListener("click", async () => {
  const feedback = byId("handoff-copy-status");
  if (!state.handoffText) {
    feedback.textContent = "Chưa có run để tạo tóm tắt.";
    return;
  }
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard API is unavailable");
    await navigator.clipboard.writeText(state.handoffText);
    feedback.textContent = "Đã sao chép tóm tắt không chứa transcript.";
  } catch (_) {
    feedback.textContent = "Không thể sao chép tự động. Hãy chọn và sao chép nội dung tóm tắt bên dưới.";
  }
});
byId("refresh-operator").addEventListener("click", () => {
  loadOperatorSettings().catch((error) => setOperatorStatus(`Không tải được cấu hình: ${error.message}`, true));
});
byId("copy-operator-setup").addEventListener("click", () => copyOperatorCommand(
  OPERATOR_RUNBOOK,
  "Đã sao chép toàn bộ runbook. Chạy từng lệnh trong terminal cục bộ; token không được dán vào browser.",
));
byId("copy-operator-apply").addEventListener("click", () => copyOperatorCommand(
  OPERATOR_APPLY_COMMAND,
  "Đã sao chép lệnh build và restart. Chạy sau khi đã lưu settings.env.",
));
byId("setup-adapter").addEventListener("change", () => {
  updateArtifactFields();
  updateLocalSetupButton();
});
["setup-model-version", "setup-preprocessing-version", "setup-threshold"].forEach((id) => {
  byId(id).addEventListener("input", updateLocalSetupButton);
});
byId("setup-confirm").addEventListener("change", updateLocalSetupButton);
byId("cancel-local-setup").addEventListener("click", () => {
  if (state.operatorSettings) renderLocalSetupForm(state.operatorSettings);
  setLocalSetupStatus("Đã hủy. Không có cấu hình nào được gửi hoặc lưu.");
});
byId("local-setup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!byId("setup-confirm").checked) {
    setLocalSetupStatus("Hãy xác nhận trước khi lưu và chạy.", true);
    return;
  }
  const adapter = byId("setup-adapter").value;
  const payload = {
    vexa_api_key: byId("setup-vexa-key").value.trim() || undefined,
    classifier_adapter: adapter,
    model_version: byId("setup-model-version").value.trim(),
    preprocessing_version: byId("setup-preprocessing-version").value.trim(),
    sentiment_confidence_threshold: Number(byId("setup-threshold").value),
    model_artifact_dir: adapter === "tfidf-logreg" ? byId("setup-artifact-dir").value.trim() || undefined : undefined,
    model_artifact_sha256: adapter === "tfidf-logreg" ? byId("setup-artifact-sha256").value.trim() || undefined : undefined,
  };
  if (!Number.isFinite(payload.sentiment_confidence_threshold) || payload.sentiment_confidence_threshold < 0 || payload.sentiment_confidence_threshold > 1) {
    setLocalSetupStatus("Confidence threshold phải trong khoảng 0 đến 1.", true);
    return;
  }
  const button = byId("submit-local-setup");
  button.disabled = true;
  setLocalSetupStatus("Đang lưu cấu hình cục bộ và lên lịch build/recreate. Dashboard sẽ tự tải lại sau khoảng 15 giây…");
  try {
    await json("/v1/operator/setup", { method: "POST", body: JSON.stringify(payload) });
    byId("setup-vexa-key").value = "";
    window.setTimeout(() => window.location.reload(), 15000);
  } catch (error) {
    setLocalSetupStatus(`Không thể lưu cấu hình: ${error.message}`, true);
    updateLocalSetupButton();
  }
});

updateStartMeetingButton();
loadOperatorSettings().catch((error) => setOperatorStatus(`Không tải được cấu hình: ${error.message}`, true));
loadLatestMeeting().catch(showError);
