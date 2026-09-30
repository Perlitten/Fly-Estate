export type Decision = "waiting" | "approach" | "avoid" | "maybe" | "no_photo";
export type Settings = {
  budget: number;
  ceiling: number;
  min_bedrooms: number;
  covered_parking: boolean;
  excluded: string[];
  ideal: [number, number];
  radius: number;
  mode: "pure" | "cyborg";
};
export type Prediction = {
  source?: "rate" | "spiking-memory";
  decision: Decision;
  probability: number;
  distance: number | null;
  price_aversion: number;
  trace: Record<string, number>;
};
export type PhotoSignals = {
  attributes: Record<string, number>;
  retina: number[];
  semantic: number[];
};
export type Listing = {
  id: string;
  url: string;
  title: string;
  price: number;
  bedrooms: number;
  size: number;
  area: string;
  city: string;
  parking: string;
  balcony: boolean;
  balcony_size: number | null;
  balcony_covered: boolean | null;
  size_kind?: "internal" | "total" | "unknown";
  field_sources?: Record<
    string,
    { url: string | null; field: string; method: string }
  >;
  evaluation_only?: boolean;
  apartment_group?: number;
  stimulus_context?: Record<
    string,
    { value: number | null; source: string; km?: number; area_kind?: string }
  >;
  freshness?: {
    checked_at: string | null;
    age_days: number | null;
    stale: boolean;
    available: boolean | null;
    gallery_version: string | null;
    sources: number;
  };
  furnished: boolean;
  coords: [number, number] | null;
  coord_kind: string;
  photos: string[];
  photo_urls: string[];
  photo_downloads?: {
    url: string;
    status: "available" | "cached" | "unavailable";
    path?: string;
    error?: string;
    captured_at: string;
  }[];
  captured_at: string;
  updated_at: string;
  published_at: string;
  vision:
    | (PhotoSignals & {
        per_photo?: PhotoSignals[];
        photos_analyzed: number;
        encoder: string;
      })
    | null;
  prediction: Prediction;
  filter_reasons: string[];
  rating: number | null;
  teacher_review?: {
    stale?: boolean;
    actor: "agent";
    value: number;
    confidence: string;
    reasons: string[];
    unknowns: string[];
    inspected_photo_sha256: string[];
    photo_notes: string[];
    price_per_m2: number | null;
  } | null;
  description: string;
  import_warnings: string[];
};
export type Data = {
  settings: Settings;
  listings: Listing[];
  ratings: Record<string, number>;
  comparisons: { a: string; b: string; choice: number }[];
  brain: {
    neurons: number;
    connections: number;
    synapses: number;
    groups: Record<string, number>;
    dataset: string;
    visual_inputs: number;
    mbon_outputs: number;
    cx_output_types: number;
    navigation_inputs: number;
    metadata_inputs: number;
  };
  training: {
    ratings: number;
    comparisons: number;
    ready: boolean;
    has_both_classes: boolean;
    next: string;
  };
  areas: Record<string, { coords: [number, number]; source: string }>;
};
export type Job = {
  id: string;
  status: "running" | "done" | "error";
  phase: string;
  total: number;
  done: number;
  imported: number;
  listing_ids?: string[];
  errors: string[];
  warnings: string[];
  error?: string;
  source?: "import" | "bazaraki";
  started_at?: string;
};
export type SpikingSummary = {
  kc_active: number;
  kc_active_fraction: number;
  mbon_spikes: number;
  pam_hz: number;
  total_spikes: number;
  wall_seconds: number;
};
export type PhotoReadiness =
  | "ready"
  | "stale"
  | "queued"
  | "running"
  | "error"
  | "missing"
  | "unavailable";
export type SimulationJob = {
  id: string;
  listing_id: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  total: number;
  done: number;
  cached: number;
  failed: number;
  error: string | null;
  cancel_requested: number;
};
export type Gallery = {
  listing_id: string;
  mode: "pure" | "cyborg";
  codec: string;
  params: {
    mode: string;
    brief: { ceiling: number; ideal: number[]; radius: number };
  };
  photos: {
    position: number;
    photo: string;
    status: PhotoReadiness;
    signals: number[] | null;
    result: SpikingSummary | null;
    error?: string;
    replay_key?: string | null;
  }[];
  counts: Partial<Record<PhotoReadiness, number>>;
  total: number;
  job: SimulationJob | null;
  live: {
    job_id: string;
    position: number;
    bins: number;
    bin_ms: number;
  } | null;
  engine: {
    version: string | null;
    fingerprint: string | null;
    worker: { alive: boolean; heartbeat_age_s?: number };
  };
};
export type SpikingReplay = {
  memory_phase?: "before" | "after";
  available: true;
  listing_id: string;
  position: number;
  live: boolean;
  bins: number;
  bin_ms: number;
  duration_ms: number;
  indices: number[];
  values: string;
  simulated_neurons: number;
  mapped_neurons: number;
  display_max_spikes_per_bin: number;
  total_spikes: number;
  checkpoint: string | null;
  fingerprint: string;
};
export type MarketOffer = {
  id: string;
  url: string;
  title: string;
  price: number | null;
  bedrooms: number | null;
  size: number | null;
  city: string;
  area: string;
  published: string | null;
  photos: number | null;
  thumb: string | null;
  coords: [number, number] | null;
  coord_kind: "source" | "area" | "unknown";
  listing_id: string | null;
  excluded_area: boolean;
};
export type Market = {
  source: string;
  fetched_at: string;
  search: string;
  pages: number;
  total_pages: number | null;
  listed: number | null;
  scanned: number;
  exact_coords: number;
  imported: number;
  new: number;
  offers: MarketOffer[];
};
