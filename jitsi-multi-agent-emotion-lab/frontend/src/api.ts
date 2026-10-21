import type { Agent, DiscussionSession } from "./types";

export const apiBase = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "The lab API could not complete that request.");
  }
  return response.json() as Promise<T>;
}

export const api = {
  agents: () => request<Agent[]>("/api/agents"),
  history: () => request<DiscussionSession[]>("/api/sessions"),
  session: (id: string) => request<DiscussionSession>(`/api/sessions/${id}`),
  create: (topic: string, rounds: number) =>
    request<DiscussionSession>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ topic, rounds }),
    }),
  action: (id: string, action: "pause" | "resume" | "stop") =>
    request<DiscussionSession>(`/api/sessions/${id}/${action}`, { method: "POST" }),
  addMessage: (id: string, message: string) =>
    request<DiscussionSession>(`/api/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  diagnostics: () => request<Record<string, string>>("/api/jitsi/diagnostics"),
};

