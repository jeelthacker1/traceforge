export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}
export type Event = {
  id: string;
  timestamp: string;
  service: string;
  kind: string;
  origin: string;
  trace_id: string | null;
  span_id: string | null;
  parent_span_id: string | null;
  account: string | null;
  source: string | null;
  attributes: Record<string, unknown>;
};
export type Alert = {
  id: string;
  rule_id: string;
  timestamp: string;
  severity: string;
  evidence: string[];
  detail: {
    name: string;
    observed: number;
    threshold: number;
    limitations: string;
    origin: string;
  };
  state: {
    acknowledged: boolean;
    assignee: string | null;
    resolution: string | null;
    escalated?: boolean;
  };
};
export type Incident = {
  id: string;
  start: string;
  end: string;
  status: string;
  detection_ids: string[];
  limitations: string;
};
export type GraphData = {
  nodes: {
    id: string;
    events: number;
    error_rate: number;
    latency_ms: number | null;
  }[];
  edges: {
    source: string;
    target: string;
    count: number;
    relationship: string;
  }[];
  missing_parents: number;
  limitations: string;
  truncated?: boolean;
};
export type Detail = Incident & {
  events: Event[];
  detections: Alert[];
  notes: {
    id: number;
    author: string;
    text: string;
    bookmark: string | null;
  }[];
  graph: GraphData;
  baseline_graph: GraphData;
  hypotheses: string[];
  unresolved_questions: string[];
};
export type Overview = {
  events: number;
  services: number;
  alerts: number;
  auth_failures: number;
  error_rate: number | null;
  latency_ms: number | null;
  pending: number;
  lag_seconds: number;
  trend: { time: string; events: number }[];
  pipeline: {
    queue?: number;
    dead_letters?: number;
    ingestion_worker?: boolean;
    correlation_worker?: boolean;
    available?: boolean;
  };
  truncated: boolean;
  anomalies: {
    service: string;
    observed: number;
    baseline: number | null;
    z_score: number | null;
    reason: string;
    anomalous: boolean | null;
  }[];
};
export type Rule = {
  id: string;
  name: string;
  enabled: boolean;
  threshold: number;
  window_seconds: number;
  severity: string;
  required: string[];
  limitations: string;
  suppressed_services: string[];
  allowed_edges: string[][];
};
