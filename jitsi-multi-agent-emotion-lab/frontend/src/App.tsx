import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { api, apiBase } from "./api";
import type { Agent, DiscussionSession, Features, Turn } from "./types";

type View = "discussion" | "audio" | "emotion" | "jitsi" | "history";

const tabs: Array<{ id: View; label: string }> = [
  { id: "discussion", label: "Discussion control" },
  { id: "audio", label: "Audio analysis" },
  { id: "emotion", label: "Emotion analysis" },
  { id: "jitsi", label: "Jitsi integration" },
  { id: "history", label: "Experiment history" },
];

const statusText: Record<string, string> = {
  created: "Preparing",
  running: "In progress",
  paused: "Paused",
  stopped: "Stopped",
  completed: "Complete",
  failed: "Needs attention",
};

function format(value: number | null | undefined, fraction = 3): string {
  return typeof value === "number" ? value.toFixed(fraction) : "—";
}

function Chart({ values, color = "#6ee7ce", empty = "No track available" }: {
  values: Array<number | null>;
  color?: string;
  empty?: string;
}) {
  const valid = values.map((value) => (value === null ? 0 : value));
  if (!valid.length) return <div className="chart-empty">{empty}</div>;
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;
  const points = valid
    .map((value, index) => `${(index / Math.max(valid.length - 1, 1)) * 100},${96 - ((value - min) / range) * 88}`)
    .join(" ");
  return (
    <svg className="chart" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Acoustic feature chart">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function MelImage({ features }: { features: Features }) {
  const rows = features.mel_spectrogram_db;
  if (!rows.length) return <div className="chart-empty">Install librosa to render a Mel-spectrogram.</div>;
  const flattened = rows.flat();
  const min = Math.min(...flattened);
  const max = Math.max(...flattened);
  return (
    <div className="mel" aria-label="Mel-spectrogram">
      {rows.flatMap((row, rowIndex) =>
        row.map((value, columnIndex) => {
          const lightness = 14 + ((value - min) / Math.max(max - min, 1)) * 63;
          return <i key={`${rowIndex}-${columnIndex}`} style={{ backgroundColor: `hsl(${195 + lightness}, 76%, ${lightness}%)` }} />;
        }),
      )}
    </div>
  );
}

function AgentBadge({ agent, agents }: { agent: string | null; agents: Agent[] }) {
  const config = agents.find((item) => item.id === agent);
  return <span className={`agent-badge ${agent || "user"}`}>{config?.label || (agent === null ? "Researcher" : agent)}</span>;
}

function turnWithAudio(session: DiscussionSession | null, selected: string | null): Turn | null {
  if (!session) return null;
  return session.turns.find((turn) => turn.id === selected) || session.turns.find((turn) => turn.audio_url) || null;
}

export default function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [session, setSession] = useState<DiscussionSession | null>(null);
  const [history, setHistory] = useState<DiscussionSession[]>([]);
  const [topic, setTopic] = useState("How can a meeting assistant make collaboration more inclusive without surveilling people?");
  const [rounds, setRounds] = useState(1);
  const [message, setMessage] = useState("");
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const [view, setView] = useState<View>("discussion");
  const [diagnostics, setDiagnostics] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedTurn = useMemo(() => turnWithAudio(session, selectedTurnId), [session, selectedTurnId]);
  const canStart = topic.trim().length >= 3 && !busy && session?.status !== "running";

  useEffect(() => {
    Promise.all([api.agents(), api.history()])
      .then(([nextAgents, sessions]) => {
        setAgents(nextAgents);
        setHistory(sessions);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!session || !["created", "running", "paused"].includes(session.status)) return;
    const poll = window.setInterval(() => {
      api.session(session.id)
        .then((next) => {
          setSession(next);
          setHistory((previous) => [next, ...previous.filter((item) => item.id !== next.id)]);
        })
        .catch((reason: Error) => setError(reason.message));
    }, 1400);
    return () => window.clearInterval(poll);
  }, [session?.id, session?.status]);

  async function createSession() {
    try {
      setBusy(true);
      setError(null);
      const next = await api.create(topic, rounds);
      setSession(next);
      setSelectedTurnId(null);
      setHistory((previous) => [next, ...previous.filter((item) => item.id !== next.id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the experiment.");
    } finally {
      setBusy(false);
    }
  }

  async function action(action: "pause" | "resume" | "stop") {
    if (!session) return;
    try {
      setError(null);
      setSession(await api.action(session.id, action));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Action failed.");
    }
  }

  async function submitMessage(event: FormEvent) {
    event.preventDefault();
    if (!session || !message.trim()) return;
    try {
      const next = await api.addMessage(session.id, message);
      setSession(next);
      setMessage("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Message could not be recorded.");
    }
  }

  async function openJitsi() {
    try {
      setDiagnostics(await api.diagnostics());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Diagnostics unavailable.");
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brand-mark">⌁</span><span>Emotion Research Lab</span><small>Synthetic discussions</small></div>
        <div className="top-status"><span className={`status-dot ${session?.status || "idle"}`} /> {session ? statusText[session.status] : "No active study"}</div>
      </header>

      <nav className="navigation" aria-label="Research lab views">
        {tabs.map((tab) => <button key={tab.id} className={view === tab.id ? "active" : ""} onClick={() => setView(tab.id)}>{tab.label}</button>)}
      </nav>

      {error && <div className="notice error" role="alert">{error}<button onClick={() => setError(null)}>Dismiss</button></div>}
      <div className="notice safety">Research prototype · Synthetic voices are clearly labeled AI bots · Acoustic features are not an emotion, depression, or clinical assessment.</div>

      {view === "discussion" && <section className="view split-layout">
        <aside className="control-panel panel">
          <p className="eyebrow">Experiment setup</p>
          <h1>Run a bounded four-agent discussion.</h1>
          <label>Research topic<textarea value={topic} onChange={(event) => setTopic(event.target.value)} rows={5} disabled={session?.status === "running"} /></label>
          <label>Discussion rounds
            <div className="stepper"><button onClick={() => setRounds((value) => Math.max(1, value - 1))} aria-label="Decrease rounds">−</button><strong>{rounds}</strong><button onClick={() => setRounds((value) => Math.min(8, value + 1))} aria-label="Increase rounds">+</button></div>
          </label>
          <div className="control-actions">
            <button className="primary" onClick={createSession} disabled={!canStart}>{busy ? "Starting…" : "Start discussion"}</button>
            <button onClick={() => action(session?.status === "paused" ? "resume" : "pause")} disabled={!session || !["running", "paused"].includes(session.status)}>{session?.status === "paused" ? "Resume" : "Pause"}</button>
            <button className="danger" onClick={() => action("stop")} disabled={!session || !["created", "running", "paused"].includes(session.status)}>Stop</button>
          </div>
          <div className="agent-grid">
            {agents.map((agent) => <article key={agent.id} className={`agent-card ${agent.id}`}><span>{agent.label}</span><small>{agent.personality}</small><em>{agent.voice} · {agent.speaking_style}</em></article>)}
          </div>
        </aside>
        <section className="timeline panel">
          <div className="section-heading"><div><p className="eyebrow">Live timeline</p><h2>{session?.topic || "Waiting for a research topic"}</h2></div>{session && <span className="session-id">{session.id.slice(0, 8)}</span>}</div>
          {!session && <div className="empty-state"><span>◌</span><p>Start an experiment to observe explicit turn-taking, generated audio, and feature extraction.</p></div>}
          {session?.turns.map((turn) => <article className="turn" key={turn.id} onClick={() => { if (turn.audio_url) { setSelectedTurnId(turn.id); setView("audio"); } }}>
            <div className="turn-meta"><AgentBadge agent={turn.agent_id} agents={agents} /><span>Round {turn.round_number} · Turn {turn.sequence}</span>{turn.audio_url && <button className="inspect">Inspect audio →</button>}</div>
            <p>{turn.transcript}</p>
            {turn.generation_backend && <small className="provenance">{turn.generation_backend} · {turn.feature_extraction_version}</small>}
          </article>)}
          {session && <form className="message-form" onSubmit={submitMessage}><input value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Add a researcher message for the next turn…" /><button disabled={!message.trim()}>Add context</button></form>}
        </section>
      </section>}

      {view === "audio" && <AudioView turn={selectedTurn} onSelect={setSelectedTurnId} turns={session?.turns || []} />}
      {view === "emotion" && <EmotionView turn={selectedTurn} agents={agents} />}
      {view === "jitsi" && <JitsiView diagnostics={diagnostics} onCheck={openJitsi} selectedTurn={selectedTurn} />}
      {view === "history" && <HistoryView history={history} select={(item) => { setSession(item); setView("discussion"); }} />}
    </main>
  );
}

function AudioView({ turn, turns, onSelect }: { turn: Turn | null; turns: Turn[]; onSelect: (id: string) => void }) {
  const features = turn?.features;
  return <section className="view analysis-view">
    <div className="section-heading"><div><p className="eyebrow">Audio analysis</p><h1>Inspect generated artifacts, not people.</h1></div><select value={turn?.id || ""} onChange={(event) => onSelect(event.target.value)}><option value="">Choose an agent turn</option>{turns.filter((item) => item.audio_url).map((item) => <option key={item.id} value={item.id}>Round {item.round_number} · {item.agent_id}</option>)}</select></div>
    {!turn || !features ? <div className="panel empty-state"><span>⌁</span><p>Select a generated agent turn from a completed discussion.</p></div> : <>
      <div className="audio-player panel"><div><AgentBadge agent={turn.agent_id} agents={[]} /><h2>{turn.intended_style}</h2><p>{turn.generation_backend}</p></div><audio controls src={`${apiBase}${turn.audio_url}`} /></div>
      <div className="metric-row">{[["Duration", `${format(features.duration_seconds, 2)} s`], ["Sample rate", `${features.sample_rate} Hz`], ["RMS energy", format(features.rms_energy)], ["Mean pitch", `${format(features.pitch_hz, 1)} Hz`], ["ZCR", format(features.zero_crossing_rate)]].map(([label, value]) => <article className="metric" key={label}><small>{label}</small><strong>{value}</strong></article>)}</div>
      <div className="analysis-grid"><Figure title="Waveform" note="Amplitude through the generated WAV"><Chart values={features.waveform} /></Figure><Figure title="Pitch track" note="Fundamental frequency (Hz)"><Chart values={features.pitch_track_hz} color="#faa66c" empty="No reliable voiced pitch detected." /></Figure><Figure title="RMS energy" note="Frame-level loudness proxy"><Chart values={features.rms_track} color="#98aafc" /></Figure><Figure title="Mel-spectrogram" note="40 Mel bands × time frames"><MelImage features={features} /></Figure><Figure title="MFCC" note="First 13 coefficients"><Matrix values={features.mfcc} /></Figure></div>
      {features.analysis_note && <p className="analysis-note">{features.analysis_note}</p>}
    </>}
  </section>;
}

function Figure({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return <figure className="figure panel"><figcaption><strong>{title}</strong><span>{note}</span></figcaption>{children}</figure>;
}

function Matrix({ values }: { values: number[][] }) {
  if (!values.length) return <div className="chart-empty">No MFCC data available.</div>;
  const data = values.flat(); const min = Math.min(...data); const max = Math.max(...data);
  return <div className="matrix">{values.flatMap((row, i) => row.map((value, j) => <i key={`${i}-${j}`} style={{ background: `hsl(${237 - ((value - min) / Math.max(max - min, 1)) * 125}, 78%, 57%)` }} />))}</div>;
}

function EmotionView({ turn, agents }: { turn: Turn | null; agents: Agent[] }) {
  const prediction = turn?.emotion_prediction;
  return <section className="view emotion-view"><p className="eyebrow">Emotion analysis</p><h1>Keep four concepts separate.</h1><p className="lede">This lab records a synthetic voice's requested style and exposes a future acoustic model interface. It does not equate style, text, acoustic features, or depression risk.</p>
    <div className="four-up"><article className="panel concept"><span>01</span><h2>Intended voice style</h2><p>{turn?.intended_style || "Choose a generated turn"}</p><small>Configured at TTS request time; not a measured emotion.</small></article><article className="panel concept"><span>02</span><h2>Text emotion</h2><p>Not inferred by default</p><small>Add a separately validated, labeled text-analysis module before reporting a result.</small></article><article className="panel concept"><span>03</span><h2>Acoustic model result</h2><p>{prediction?.label || "Unavailable"}</p><small>{prediction?.reason || "No audio turn selected."}</small></article><article className="panel concept caution"><span>04</span><h2>Depression risk</h2><p>Out of scope</p><small>This prototype must not diagnose, screen, or score depression risk.</small></article></div>
    {turn && <div className="panel detail-row"><AgentBadge agent={turn.agent_id} agents={agents} /><div><strong>Model status: {prediction?.status || "unavailable"}</strong><p>Model version: {prediction?.model_version || "not configured"} · Confidence: {prediction?.confidence ?? "not reported"}</p></div></div>}
  </section>;
}

function JitsiView({ diagnostics, onCheck, selectedTurn }: { diagnostics: Record<string, string> | null; onCheck: () => void; selectedTurn: Turn | null }) {
  return <section className="view jitsi-view"><div className="section-heading"><div><p className="eyebrow">Jitsi integration</p><h1>Route one generated WAV at a time.</h1></div><button className="primary" onClick={onCheck}>Check host diagnostics</button></div><div className="jitsi-grid"><article className="panel"><h2>1. Create virtual devices</h2><code>./scripts/setup_virtual_audio.sh</code><p>Creates a PulseAudio/PipeWire-compatible null sink and monitor source. Select <b>JitsiLabMic</b> as the microphone in Jitsi.</p></article><article className="panel"><h2>2. Play sequentially</h2><code>./scripts/play_audio_to_jitsi.sh data/media/&lt;session&gt;/&lt;turn&gt;.wav</code><p>Use this for a selected WAV; the script serializes one playback process with a lock.</p></article><article className="panel"><h2>3. Respect the boundary</h2><p>Iframe embedding controls meetings but does not provide raw participant audio tracks. Future incoming-audio research needs an approved media adapter and explicit consent.</p></article></div>{selectedTurn && <div className="panel selected-queue"><span>Queued sample</span><strong>{selectedTurn.agent_id} · round {selectedTurn.round_number}</strong><small>{selectedTurn.audio_url?.replace("/api/", "")}</small></div>}{diagnostics && <dl className="diagnostics panel">{Object.entries(diagnostics).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl>}</section>;
}

function HistoryView({ history, select }: { history: DiscussionSession[]; select: (session: DiscussionSession) => void }) {
  return <section className="view"><div className="section-heading"><div><p className="eyebrow">Experiment history</p><h1>Persisted sessions and portable exports.</h1></div></div><div className="history-list">{history.length === 0 ? <div className="panel empty-state"><p>No session has been created yet.</p></div> : history.map((item) => <article className="panel history-item" key={item.id}><div><span className={`status-pill ${item.status}`}>{statusText[item.status]}</span><h2>{item.topic}</h2><p>{item.completed_rounds}/{item.requested_rounds} rounds · {item.turns.length || "—"} visible turns</p><small>{item.id}</small></div><div className="history-actions"><button onClick={() => select(item)}>Open</button><a href={`${apiBase}/api/sessions/${item.id}/export.json`} target="_blank">JSON</a><a href={`${apiBase}/api/sessions/${item.id}/export.csv`} target="_blank">CSV</a></div></article>)}</div></section>;
}
