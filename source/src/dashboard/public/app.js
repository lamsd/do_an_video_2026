const state = { meetingId: null, meeting: null, stream: null, refreshTimer: null };
const byId = (id) => document.getElementById(id);
const api = (path, options = {}) => fetch(`/api${path}`, {
  ...options,
  headers: { "Content-Type": "application/json", ...options.headers },
});
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function setStatus(value) { byId("status").textContent = value; }
function ratio(value) { return `${Math.round((value || 0) * 100)}%`; }
function score(value) { return value == null ? "Không đủ dữ liệu" : value.toFixed(2); }

async function json(path, options) {
  const response = await api(path, options);
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json();
}

function renderActiveMeeting() {
  const element = byId("active-meeting");
  if (!state.meeting) { element.hidden = true; return; }
  element.textContent = `Meeting đang xem: ${state.meetingId} · ${state.meeting.status}`;
  element.hidden = false;
}

function renderTranscript(rows) {
  const container = byId("transcript");
  container.replaceChildren();
  byId("transcript-meta").textContent = `${rows.length} segment · tự cập nhật khi Vexa có transcript mới`;
  if (!rows.length) {
    container.textContent = "Chưa có transcript final. Hãy admit bot, nói rõ 15–20 giây và chờ STT xử lý.";
  } else {
    rows.forEach((row) => {
      const article = document.createElement("article");
      article.className = "transcript-item";
      const meta = document.createElement("small");
      meta.textContent = `${row.speaker || "Chưa gán speaker"} · ${row.is_final ? "final" : "draft"} · ${row.start.toFixed(1)}s`;
      const text = document.createElement("p");
      text.textContent = row.text;
      article.append(meta, text);
      container.append(article);
    });
  }
  byId("transcript-section").hidden = false;
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
    point.addEventListener("click", loadEvidence);
    element.append(point);
  });
}

function renderEvidence(rows) {
  const container = byId("evidence");
  container.replaceChildren();
  if (!rows.length) { container.textContent = "Chưa có evidence phân tích."; return; }
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
  if (!state.meetingId || !UUID.test(state.meetingId)) return;
  const [transcript, overview, timeline] = await Promise.all([
    json(`/v1/meetings/${state.meetingId}/transcript`),
    json(`/v1/meetings/${state.meetingId}/analytics/overview`),
    json(`/v1/meetings/${state.meetingId}/analytics/timeline`),
  ]);
  renderTranscript(transcript);
  renderOverview(overview);
  renderTimeline(timeline);
  await loadEvidence();
  byId("timeline-section").hidden = false;
  setStatus(`Transcript ${transcript.length} segment · Analysis ${overview.status} · revision ${overview.source_revision ?? "—"}`);
}

function scheduleRefresh() {
  clearTimeout(state.refreshTimer);
  state.refreshTimer = setTimeout(() => refresh().catch(showError), 300);
}

function connectEvents() {
  state.stream?.close();
  state.stream = new EventSource(`/api/v1/meetings/${state.meetingId}/events`);
  state.stream.addEventListener("transcript.segment.upserted", scheduleRefresh);
  state.stream.addEventListener("analysis.sentiment.updated", scheduleRefresh);
}

function showError(error) { setStatus(`Không tải được dashboard: ${error.message}`); }

async function selectMeeting(meeting) {
  if (!meeting?.id || !UUID.test(meeting.id)) throw new Error("Meeting ID không hợp lệ");
  state.meetingId = meeting.id;
  state.meeting = meeting;
  byId("meeting-id").value = meeting.id;
  renderActiveMeeting();
  await refresh();
  connectEvents();
}

async function loadLatestMeeting() {
  const meetings = await json("/v1/meetings?limit=1");
  if (!meetings.length) {
    setStatus("Chưa có meeting nào. Tạo bot qua POST /v1/meetings trước.");
    return;
  }
  await selectMeeting(meetings[0]);
}

byId("meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = byId("meeting-id").value.trim();
  try {
    if (!id) return await loadLatestMeeting();
    await selectMeeting(await json(`/v1/meetings/${id}`));
  } catch (error) { showError(error); }
});

byId("run-final").addEventListener("click", async () => {
  if (!state.meetingId) return setStatus("Chưa có meeting để phân tích.");
  try {
    await json(`/v1/meetings/${state.meetingId}/analysis?kind=final`, { method: "POST" });
    await refresh();
  } catch (error) { setStatus(`Không thể tạo job: ${error.message}`); }
});

loadLatestMeeting().catch(showError);
