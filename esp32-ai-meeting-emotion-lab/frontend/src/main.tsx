import { StrictMode, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import type { Agent, Device, ExperimentSession, Turn } from "./types";
import "./styles.css";

const formatTime = (value: string | null) =>
  value ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value)) : "—";

function audioFeatures(turn: Turn) {
  const data = turn.acoustic_metadata ?? {};
  return [
    ["RMS", data.rms_energy],
    ["Cao độ", data.pitch_hz ? `${data.pitch_hz} Hz` : "—"],
    ["Thời lượng", data.duration_seconds ? `${data.duration_seconds} giây` : "—"],
    ["Trích đặc trưng", data.feature_version ?? "—"],
  ];
}

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [current, setCurrent] = useState<ExperimentSession | null>(null);
  const [topic, setTopic] = useState("Thiết kế cuộc họp AI minh bạch và tôn trọng quyền riêng tư");
  const [rounds, setRounds] = useState(1);
  const [notice, setNotice] = useState("Đang kết nối với bộ điều phối…");

  const refresh = useCallback(async () => {
    try {
      const [nextAgents, nextDevices, sessions] = await Promise.all([api.agents(), api.devices(), api.sessions()]);
      setAgents(nextAgents);
      setDevices(nextDevices);
      const newest = sessions[0] ?? null;
      if (newest) setCurrent(await api.session(newest.id));
      else setCurrent(null);
      setNotice("Bộ điều phối sẵn sàng.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không thể tải trạng thái.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const deviceByAgent = useMemo(() => new Map(devices.map((device) => [device.agent_id, device])), [devices]);
  const allOnline = devices.length === 4 && devices.every((device) => device.state !== "disconnected");

  async function start() {
    try {
      setNotice("Đang tạo phiên thảo luận…");
      const session = await api.start(topic, rounds);
      setCurrent(await api.session(session.id));
      setNotice("Đã cấp lượt điều phối đầu tiên.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không thể bắt đầu phiên.");
    }
  }

  async function control(action: "pause" | "resume" | "stop") {
    if (!current) return;
    try {
      setCurrent(await api.control(current.id, action));
      setNotice(action === "pause" ? "Phiên đã tạm dừng." : action === "resume" ? "Phiên đang tiếp tục." : "Phiên đã dừng.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không thể điều khiển phiên.");
    }
  }

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Bài khóa luận · Mô phỏng phân tán</p>
        <h1>ESP32 AI Meeting Emotion Lab</h1>
        <p>Bốn thiết bị vật lý, một bộ điều phối MQTT, tác nhân và giọng nói tổng hợp chạy ở Ubuntu backend.</p>
        <p className="notice" role="status">{notice}</p>
      </header>

      <section className="devices" aria-label="Bốn tác nhân ESP32">
        {agents.map((agent) => {
          const device = deviceByAgent.get(agent.agent_id);
          return (
            <article className="device" key={agent.agent_id}>
              <div className={`state ${device?.state ?? "disconnected"}`}>{device?.state ?? "disconnected"}</div>
              <h2>{agent.display_name}</h2>
              <p>{agent.device_id} · giọng <code>{agent.voice}</code></p>
              <p>{agent.personality}</p>
              <small>Jitsi: {agent.meeting_participant_id} · {formatTime(device?.last_seen_at ?? null)}</small>
            </article>
          );
        })}
      </section>

      <section className="grid">
        <form className="panel composer" onSubmit={(event) => { event.preventDefault(); void start(); }}>
          <p className="eyebrow">Điều khiển phiên</p>
          <h2>Đề tài thảo luận</h2>
          <label htmlFor="topic">Chủ đề</label>
          <textarea id="topic" value={topic} onChange={(event) => setTopic(event.target.value)} minLength={3} maxLength={2000} />
          <label htmlFor="rounds">Số vòng (1–8)</label>
          <input id="rounds" type="number" min="1" max="8" value={rounds} onChange={(event) => setRounds(Number(event.target.value))} />
          <button disabled={!allOnline || current?.status === "running"}>Bắt đầu thảo luận</button>
          <small>{allOnline ? "Cả bốn thiết bị đã trực tuyến." : "Cần đủ bốn ESP32 trực tuyến trước khi bắt đầu."}</small>
        </form>

        <section className="panel status-panel">
          <p className="eyebrow">Phiên hiện tại</p>
          <h2>{current?.topic ?? "Chưa có phiên"}</h2>
          <p>Trạng thái: <strong>{current?.status ?? "waiting_for_devices"}</strong></p>
          <p>Vòng hoàn tất: {current?.completed_rounds ?? 0}/{current?.requested_rounds ?? 0} · {current?.turns.length ?? 0} lượt</p>
          <div className="controls">
            <button type="button" onClick={() => void control("pause")} disabled={current?.status !== "running"}>Tạm dừng</button>
            <button type="button" onClick={() => void control("resume")} disabled={current?.status !== "paused"}>Tiếp tục</button>
            <button className="danger" type="button" onClick={() => void control("stop")} disabled={!current || !["running", "paused"].includes(current.status)}>Dừng</button>
          </div>
          <p className="boundary">Nhãn cảm xúc là mô hình nghiên cứu riêng; hệ thống không suy luận trầm cảm từ âm thanh.</p>
        </section>
      </section>

      <section className="panel transcript">
        <p className="eyebrow">Bản ghi chung</p>
        <h2>Lịch sử theo token điều phối</h2>
        {current?.turns.length ? current.turns.map((turn) => {
          const agent = agents.find((item) => item.agent_id === turn.agent_id);
          return (
            <article className="turn" key={turn.id}>
              <div><span>Lượt {turn.sequence} · vòng {turn.round_number}</span><h3>{agent?.display_name ?? turn.agent_id}</h3></div>
              <p>{turn.transcript}</p>
              {turn.audio_url && <audio controls src={`${api.base}${turn.audio_url}`}>Trình duyệt không hỗ trợ phát WAV.</audio>}
              <dl>{audioFeatures(turn).map(([name, value]) => <div key={String(name)}><dt>{String(name)}</dt><dd>{String(value)}</dd></div>)}</dl>
              <small>Cảm xúc: {String(turn.emotion_prediction?.status ?? "unavailable")} · {String(turn.emotion_prediction?.reason ?? "")}</small>
            </article>
          );
        }) : <p className="empty">Các lượt được xác nhận sẽ xuất hiện ở đây.</p>}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
