const state = { meetingId: null, stream: null };
const byId = (id) => document.getElementById(id);
const api = (path, options = {}) => fetch(`/api${path}`, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });

function setStatus(value) { byId("status").textContent = value; }
function ratio(value) { return `${Math.round((value || 0) * 100)}%`; }
function score(value) { return value == null ? "Không đủ dữ liệu" : value.toFixed(2); }

async function json(path, options) {
  const response = await api(path, options);
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json();
}

function renderOverview(overview) {
  const data = [
    ["Positive", ratio(overview.ratios?.positive)], ["Neutral", ratio(overview.ratios?.neutral)],
    ["Negative", ratio(overview.ratios?.negative)], ["Coverage", ratio(overview.coverage)],
    ["Polarity", score(overview.score)], ["Model", overview.model_version || "Chưa chạy"],
  ];
  byId("metrics").innerHTML = data.map(([name, value]) => `<article class="card"><span>${name}</span><strong>${value}</strong></article>`).join("");
  byId("metrics").hidden = false;
}

function renderTimeline(rows) {
  const element = byId("timeline");
  element.replaceChildren();
  if (!rows.length) { element.textContent = "Chưa có cửa sổ phân tích."; return; }
  rows.forEach((row) => {
    const point = document.createElement("button");
    const value = row.score ?? 0;
    point.className = `point ${value > 0.1 ? "positive" : value < -0.1 ? "negative" : "neutral"}`;
    point.style.height = `${Math.max(14, Math.min(100, Math.abs(value) * 100))}%`;
    point.title = `${new Date(row.start).toLocaleTimeString()} · score ${score(row.score)} · coverage ${ratio(row.coverage)}`;
    point.addEventListener("click", () => loadEvidence(row.start, row.end));
    element.append(point);
  });
}

function renderEvidence(rows) {
  const container = byId("evidence");
  container.replaceChildren();
  if (!rows.length) { container.textContent = "Không có evidence phù hợp."; return; }
  const template = byId("evidence-item");
  rows.forEach((row) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".evidence-meta").textContent = `${row.speaker || "Chưa gán speaker"} · ${row.label} · confidence ${ratio(row.confidence)}`;
    node.querySelector("p").textContent = row.text;
    node.querySelector("small").textContent = `${new Date(row.start).toLocaleString()} · ${row.quality_status}${row.quality_reasons.length ? ` (${row.quality_reasons.join(", ")})` : ""}`;
    container.append(node);
  });
}

async function loadEvidence() {
  const rows = await json(`/v1/meetings/${state.meetingId}/analytics/units`);
  renderEvidence(rows);
  byId("evidence-section").hidden = false;
}

async function refresh() {
  if (!state.meetingId) return;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(state.meetingId)) {
    throw new Error("Meeting ID phải là Application UUID do backend trả về, không phải mã phòng Google Meet");
  }
  const [overview, timeline] = await Promise.all([
    json(`/v1/meetings/${state.meetingId}/analytics/overview`),
    json(`/v1/meetings/${state.meetingId}/analytics/timeline`),
  ]);
  renderOverview(overview); renderTimeline(timeline); await loadEvidence();
  byId("timeline-section").hidden = false;
  setStatus(`Analysis ${overview.status} · revision ${overview.source_revision ?? "—"}`);
}

function connectEvents() {
  state.stream?.close();
  state.stream = new EventSource(`/api/v1/meetings/${state.meetingId}/events`);
  state.stream.addEventListener("analysis.sentiment.updated", refresh);
}

byId("meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault(); state.meetingId = byId("meeting-id").value.trim();
  try { await refresh(); connectEvents(); } catch (error) { setStatus(`Không tải được dashboard: ${error.message}`); }
});
byId("run-final").addEventListener("click", async () => {
  if (!state.meetingId) return setStatus("Nhập Meeting ID trước.");
  try { await json(`/v1/meetings/${state.meetingId}/analysis?kind=final`, { method: "POST" }); await refresh(); }
  catch (error) { setStatus(`Không thể tạo job: ${error.message}`); }
});
