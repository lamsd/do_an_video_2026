export type Agent = {
  agent_id: string;
  device_id: string;
  display_name: string;
  meeting_participant_id: string;
  voice: string;
  personality: string;
  speaking_style: string;
};

export type Device = {
  agent_id: string;
  device_id: string;
  display_name: string;
  voice: string;
  state: string;
  firmware_version: string | null;
  last_seen_at: string | null;
  last_error: string | null;
};

export type Turn = {
  id: string;
  agent_id: string;
  sequence: number;
  round_number: number;
  transcript: string;
  voice: string;
  audio_url: string | null;
  acoustic_metadata: Record<string, unknown> | null;
  emotion_prediction: Record<string, unknown> | null;
  created_at: string | null;
};

export type ExperimentSession = {
  id: string;
  topic: string;
  requested_rounds: number;
  completed_rounds: number;
  status: "waiting_for_devices" | "running" | "paused" | "completed" | "stopped" | "failed";
  created_at: string | null;
  updated_at: string | null;
  turns: Turn[];
};
