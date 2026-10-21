const api = "http://localhost:8001";
let activeSession = null;

const el = (id) => document.getElementById(id);
const safe = (text) => String(text).replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]));

async function fetchJson(path, options) {
  const response = await fetch(`${api}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "Request failed");
  }
  return response.json();
}

function renderDevices(devices) {
  el("online-count").textContent = devices.filter((device) => device.state !== "disconnected").length;
  el("devices").innerHTML = devices.map((device) => `
    <article class="device ${safe(device.agent_id)}">
      <div><span class="dot ${safe(device.state)}"></span><small>${safe(device.device_id)}</small></div>
      <h2>${safe(device.display_name)}</h2>
      <p>${safe(device.agent_id)} · ${safe(device.voice)}</p>
      <strong>${safe(device.state)}</strong>
      <em>${device.last_seen_at ? `heartbeat ${new Date(device.last_seen_at).toLocaleTimeString()}` : "awaiting registration"}</em>
    </article>`).join("");
}

function renderSession(session) {
  activeSession = session;
  el("session-title").textContent = `${session.status} · ${session.completed_rounds}/${session.requested_rounds} rounds`;
  el("stop").disabled = session.status !== "running";
  if (!session.turns.length) {
    el("turns").className = "turns empty";
    el("turns").textContent = "The coordinator has granted the next device turn.";
    return;
  }
  el("turns").className = "turns";
  el("turns").innerHTML = session.turns.map((turn) => `
    <article class="turn ${safe(turn.agent_id)}">
      <div><span>${safe(turn.agent_id)}</span><small>Round ${turn.round_number} · sequence ${turn.sequence} · ${safe(turn.voice)}</small></div>
      <p>${safe(turn.transcript)}</p>
      <footer>${turn.audio_url ? `<audio controls src="${api}${turn.audio_url}"></audio>` : ""}<small>${safe(turn.acoustic_metadata?.feature_version || "audio pending")} · emotion: ${safe(turn.emotion_prediction?.status || "unavailable")}</small></footer>
    </article>`).join("");
}

async function refresh() {
  try {
    const [health, devices] = await Promise.all([fetchJson("/health"), fetchJson("/api/devices")]);
    el("connection").textContent = health.mqtt_configured ? "Coordinator connected" : "MQTT credentials missing";
    el("connection").className = health.mqtt_configured ? "connection up" : "connection down";
    renderDevices(devices);
    if (activeSession) renderSession(await fetchJson(`/api/sessions/${activeSession.id}`));
  } catch (error) {
    el("connection").textContent = "Backend unavailable";
    el("connection").className = "connection down";
  }
}

el("start-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  el("start-error").textContent = "";
  try {
    const session = await fetchJson("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic: el("topic").value, rounds: Number(el("rounds").value) }) });
    renderSession(session);
  } catch (error) { el("start-error").textContent = error.message; }
});

el("stop").addEventListener("click", async () => {
  if (activeSession) renderSession(await fetchJson(`/api/sessions/${activeSession.id}/stop`, { method: "POST" }));
});
el("refresh").addEventListener("click", refresh);
refresh();
setInterval(refresh, 1500);

