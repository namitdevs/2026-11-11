export type RouteStep = {
  from_node: string;
  to_node: string;
  instruction: string;
  distance_m: number;
};

export type RouteResult = {
  mode: "fastest" | "safest";
  path: string[];
  labels: string[];
  steps: RouteStep[];
  distance_m: number;
  eta_min: number;
  risk_index: number;
  risk_reduction_pct: number;
  accessible: boolean;
  night_mode: boolean;
};

export type Verification = "map" | "official" | "third-party" | "unverified" | "demo";
export type ServiceState = "connected" | "partial" | "demo" | "not_connected";

export type Place = {
  id: string;
  name: string;
  node_id: string;
  category: string;
  aliases: string[];
  floor: string;
  landmark: string;
  tone: number;
  open_hours: string;
  verification: Verification;
  source: string;
  description: string;
  popular: boolean;
};

export type Department = {
  name: string;
  school: string;
  source: string;
  verification: Verification;
};

export type ServiceStatus = {
  id: string;
  name: string;
  status: ServiceState;
  capability: string;
  detail: string;
  source: string;
};

export type GraphNode = {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
  capacity: number;
  footfall: number;
};

export type GraphEdge = {
  id: string;
  u: string;
  v: string;
  distance_m: number;
  lit: boolean;
  cctv: boolean;
  stairs: boolean;
  footfall: number;
  risk: number;
};

export type ForecastPoint = { horizon_min: number; p10: number; p50: number; p90: number };

export type ForecastBundle = {
  label: string;
  capacity: number;
  history: { ts: string; ratio: number }[];
  points: ForecastPoint[];
  model: string;
};

export type Hotspot = {
  node_id: string;
  label: string;
  occupancy_ratio: number;
  predicted_ratio: number;
  pressure: number;
  queue_len: number;
  wait_min: number;
};

export type TriageCluster = {
  cluster_id: string;
  node_id: string;
  node_label: string;
  category: string;
  merged_reports: number;
  reported_at: string;
  priority: "P0" | "P1" | "P2" | "P3";
  priority_confidence: number;
  sla_minutes: number;
  summary: string;
  playbook: string;
  evidence_ids: string[];
  evidence_snippets: string[];
  mean_similarity: number;
  embedding_backend: string;
};

export type MessPlan = {
  date: string;
  meal: string;
  mess_id: string;
  mess_label: string;
  predicted_headcount: number;
  p90_headcount: number;
  prep_kg: number;
  expected_waste_kg: number;
  baseline_waste_kg: number;
  waste_saved_kg: number;
  confidence: number;
};

export type Cart = {
  id: string;
  label: string;
  node_id: string;
  status: "available" | "on_trip" | "charging";
  capacity: number;
  progress: number;
  next_node: string | null;
};

export type Dispatch = {
  cart_id: string;
  cart_label: string;
  pickup_node: string;
  eta_min: number;
  walk_min: number;
  reason: string;
  alternatives: string[];
};

export type StressComponent = { key: string; label: string; value: number; weight: number };

export type Snapshot = {
  generated_at: string;
  mode: string;
  csi: { score: number; label: string; components: StressComponent[] };
  kpis: Record<string, string | number>;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  places: Place[];
  departments: Department[];
  services: ServiceStatus[];
  routes: Record<string, Record<string, Record<"fastest" | "safest", RouteResult>>>;
  carts: Cart[];
  dispatches: Record<string, Dispatch>;
  forecasts: Record<string, ForecastBundle>;
  hotspots: Hotspot[];
  triage: {
    queue: TriageCluster[];
    stats: { reports_last_24h: number; clusters_last_24h: number; p0_p1: number; cluster_ratio: number };
  };
  mess: MessPlan[];
  benchmark: Record<string, any>;
  insights: string[];
  refine: {
    raw_rows: number;
    accepted_rows: number;
    dropped_rows: number;
    duplicate_rows_removed: number;
    incident_reports_merged: number;
    clusters_formed: number;
    staleness_gaps: number;
    quality_score: number;
    issues: string[];
  };
};
