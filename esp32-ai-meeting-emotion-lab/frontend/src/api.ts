import type { Agent, Device, ExperimentSession } from "./types";

const apiBase = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Yêu cầu thất bại (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  base: apiBase,
  agents: () => request<Agent[]>("/api/agents"),
  devices: () => request<Device[]>("/api/devices"),
  sessions: () => request<ExperimentSession[]>("/api/sessions"),
  session: (id: string) => request<ExperimentSession>(`/api/sessions/${id}`),
  start: (topic: string, rounds: number) =>
    request<ExperimentSession>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ topic, rounds }),
    }),
  control: (id: string, action: "pause" | "resume" | "stop") =>
    request<ExperimentSession>(`/api/sessions/${id}/${action}`, { method: "POST" }),
};
