export type SessionStatus = "created" | "running" | "paused" | "stopped" | "completed" | "failed";

export interface Agent {
  id: string;
  label: string;
  personality: string;
  voice: string;
  speaking_style: string;
}

export interface Prediction {
  status: "unavailable" | "abstained" | "available";
  label: string;
  confidence: number | null;
  model_version: string | null;
  reason: string;
}

export interface Features {
  version: string;
  duration_seconds: number;
  sample_rate: number;
  rms_energy: number;
  zero_crossing_rate: number;
  pitch_hz: number | null;
  spectral_centroid_hz: number | null;
  spectral_bandwidth_hz: number | null;
  waveform: Array<number | null>;
  pitch_track_hz: Array<number | null>;
  rms_track: Array<number | null>;
  mfcc: number[][];
  mel_spectrogram_db: number[][];
  analysis_note?: string;
}

export interface Turn {
  id: string;
  sequence: number;
  round_number: number;
  speaker_type: "agent" | "user";
  agent_id: string | null;
  transcript: string;
  voice: string | null;
  intended_style: string | null;
  audio_url: string | null;
  generation_backend: string | null;
  feature_extraction_version: string | null;
  features: Features | null;
  emotion_prediction: Prediction | null;
  created_at: string | null;
}

export interface DiscussionSession {
  id: string;
  topic: string;
  requested_rounds: number;
  completed_rounds: number;
  status: SessionStatus;
  created_at: string | null;
  updated_at: string | null;
  turns: Turn[];
}

