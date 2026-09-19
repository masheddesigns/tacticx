/**
 * TacticX API Canonical TypeScript Definitions
 * Directly maps to Phase 17 Match Intelligence & Phase 18-20 Backend Contracts.
 * No calculated or synthesized fields allowed.
 */

export interface PaginatedMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface MatchListItem {
  id: number;
  league_id?: number | null;
  home_team_id?: number | null;
  away_team_id?: number | null;
  home_team_name?: string | null;
  away_team_name?: string | null;
  kickoff_at?: string | null;
  status: string;
  minute?: number | null;
  home_score?: number | null;
  away_score?: number | null;
  canonical_season?: string;
  prediction_eligible?: boolean;
}

export interface PaginatedMatchesResponse {
  data: MatchListItem[];
  meta: PaginatedMeta;
  season?: string;
}

export interface LeagueItem {
  id: number;
  code: string;
  name: string;
  country?: string | null;
  season: string;
}

export interface LeaguesResponse {
  data: LeagueItem[];
}

export interface MatchTeam {
  team_id?: number | null;
  name?: string | null;
}

export interface MatchCompetition {
  league_id?: number | null;
  code?: string | null;
  name?: string | null;
}

export interface MatchSourceMapping {
  source: string;
  source_match_id: string;
}

export interface MatchSection {
  match_id: number;
  home_team: MatchTeam;
  away_team: MatchTeam;
  competition: MatchCompetition;
  season: string;
  kickoff: string;
  venue?: string | null;
  status: string;
  sources: MatchSourceMapping[];
}

export interface CutoffSection {
  cutoff: string;
  cutoff_policy: string;
  prediction_as_of: string;
  market_as_of?: string | null;
  temporal_quality: 'strict' | 'estimated' | 'unknown' | string;
  has_estimated_timing: boolean;
  has_unknown_timing: boolean;
}

export interface ExpectedGoalsSection {
  home_lambda?: number | null;
  away_lambda?: number | null;
  total_lambda?: number | null;
  [key: string]: any;
}

export interface CorePredictionSection {
  home?: number | null;
  draw?: number | null;
  away?: number | null;
  expected_goals?: {
    home?: number | null;
    away?: number | null;
  };
  model_version?: string;
  prediction_mode?: string;
  calibration_state?: string;
  dataset_version?: string;
  feature_version?: string;
  prediction_snapshot?: {
    prediction_id?: number | null;
    hash?: string;
  };
}

export interface DerivedMarketsSection {
  one_x_two?: {
    home?: number | null;
    draw?: number | null;
    away?: number | null;
  };
  double_chance?: {
    '1x'?: number | null;
    'x2'?: number | null;
    '12'?: number | null;
    [key: string]: number | null | undefined;
  };
  totals?: Record<string, number>;
  btts?: {
    yes?: number | null;
    no?: number | null;
  };
  team_totals?: {
    status?: string;
    home?: Record<string, number>;
    away?: Record<string, number>;
  };
}

export interface CorrectScoreEntry {
  score: string;
  probability: number;
}

export interface CorrectScoreSection {
  distribution?: Record<string, number>;
  top_n?: CorrectScoreEntry[];
  required_16_mass?: number | null;
  tail_mass?: number | null;
  probability_sum?: number | null;
}

export interface UncertaintySection {
  predictive_entropy?: number | null;
  top_probability?: number | null;
  probability_margin?: number | null;
  model_disagreement?: any;
  data_completeness?: {
    home_history?: number;
    away_history?: number;
    home_xg_history?: number;
    away_xg_history?: number;
    xg_available?: boolean;
  };
  note?: string;
}

export interface ModelDisagreementMember {
  status?: string;
  version?: string;
  home?: number | null;
  draw?: number | null;
  away?: number | null;
  notes?: string[];
}

export interface ModelDisagreementOutcomeStats {
  mean?: number;
  std?: number;
  min?: number;
  max?: number;
  range?: number;
  n_members?: number;
  members?: string[];
}

export interface ModelDisagreementSection {
  members?: Record<string, ModelDisagreementMember>;
  per_outcome?: Record<string, ModelDisagreementOutcomeStats>;
  label?: string;
}

export interface DataQualitySection {
  completeness?: {
    feature_count?: number;
    available?: number;
    missing?: number;
  };
  coverage?: {
    xg_available?: boolean;
    event_data_available?: boolean;
    lineup_data_available?: boolean;
    market_available?: boolean;
  };
  source_count?: number;
  missing_families?: string[];
  conflicts?: any[];
}

export interface TemporalQualitySection {
  strict?: string[];
  estimated?: string[];
  unknown?: string[];
}

export interface OutcomeDivergence {
  model?: number;
  market?: number;
  absolute_difference?: number;
  magnitude?: string;
}

export interface MarketDivergence {
  per_outcome?: Record<string, OutcomeDivergence>;
  overall?: string;
  peak_absolute_difference?: number;
  thresholds?: {
    moderate?: number;
    large?: number;
  };
  note?: string;
}

export interface MarketSection {
  available_markets?: string[];
  bookmaker_count?: number;
  consensus?: {
    home?: number | null;
    draw?: number | null;
    away?: number | null;
  };
  model_probabilities?: {
    home?: number | null;
    draw?: number | null;
    away?: number | null;
  };
  divergence?: MarketDivergence;
  movement?: any;
  market_timing?: string | null;
  closing_used?: boolean;
  overround?: number | null;
  market_status?: string;
}

export interface AnalogueMatch {
  match_id: number;
  kickoff_at: string;
  home_team_id: number;
  away_team_id: number;
  actual: string;
  home_score: number;
  away_score: number;
  distance: number;
  similarity: number;
}

export interface AnaloguesSection {
  status?: string;
  analogues?: AnalogueMatch[];
  outcome_distribution?: {
    n: number;
    home: number;
    draw: number;
    away: number;
    note?: string;
  };
  methodology?: string;
  provenance?: any;
}

export interface ScenarioParameters {
  kind: string;
  home_mult: number;
  away_mult: number;
  description: string;
  calculation_version?: string;
}

export interface ScenarioItem {
  name: string;
  parameters: ScenarioParameters;
  probabilities: {
    home: number;
    draw: number;
    away: number;
  };
  goals: {
    home_lambda: number;
    away_lambda: number;
    total_lambda: number;
  };
  markets: Record<string, number>;
  score_top: CorrectScoreEntry[];
  difference_from_baseline?: {
    probabilities?: {
      home: number;
      draw: number;
      away: number;
    };
    goals?: {
      home_lambda: number;
      away_lambda: number;
      total_lambda: number;
    };
    markets?: Record<string, number>;
  };
  label?: string;
}

export interface MirofishSection {
  status: string; // 'unavailable' | 'ok' | 'error'
  provider: string;
  contract_version: string;
  scenarios: any[];
  provenance: any;
  reason?: string;
  error?: string;
}

export interface ExplanationFactor {
  factor: string;
  statement: string;
  source: string;
}

export interface ExplanationSection {
  headline?: string;
  factors?: ExplanationFactor[];
  elo?: any;
  poisson?: any;
  xg?: any;
  features?: any;
  model_disagreement_note?: string;
  provenance?: any;
}

export interface WarningItem {
  code: string;
  severity: string; // 'info' | 'warning' | 'error'
  detail?: string;
  message: string;
  evidence?: any;
}

export interface ProvenanceSection {
  match_id: number;
  cutoff: string;
  prediction_snapshot: any;
  model_version: string;
  feature_version: string;
  dataset_version: string;
  intelligence_snapshot: any;
  scenario_version: string;
  mirofish_contract_version: string;
  mirofish_provider: string;
  request_hash: string;
  response_hash: string;
  generated_at: string;
}

export interface MatchIntelligence {
  schema_version: string;
  match: MatchSection;
  cutoff: CutoffSection;
  core_prediction: CorePredictionSection;
  derived_markets: DerivedMarketsSection;
  expected_goals: ExpectedGoalsSection;
  correct_score: CorrectScoreSection;
  uncertainty: UncertaintySection;
  model_disagreement: ModelDisagreementSection;
  data_quality: DataQualitySection;
  temporal_quality: TemporalQualitySection;
  market: MarketSection;
  analogues: AnaloguesSection;
  scenarios: ScenarioItem[];
  mirofish: MirofishSection;
  explanation: ExplanationSection;
  warnings: WarningItem[];
  provenance: ProvenanceSection;
}

// System Status & Provider Qualification Types
export interface SourceHealthInfo {
  state?: string;
  last_success?: string | null;
  last_failure?: string | null;
  consecutive_failures?: number;
  backoff_until?: string | null;
  quota_remaining?: number | null;
  last_observed_fixture?: string | null;
}

export interface SourceEntry {
  source_id: string;
  provider_type?: string;
  tier?: string;
  enabled: boolean;
  priority: number;
  qualification_status?: string;
  capabilities?: string[];
  health?: SourceHealthInfo;
}

export interface SourcesResponse {
  sources: SourceEntry[];
}

export interface AcquisitionStatusResponse {
  health: Record<string, SourceHealthInfo>;
  qualifications: Record<string, Array<{
    status: string;
    competition?: string;
    season?: string;
    fixture_count?: number;
    retrieved_at?: string;
  }>>;
  freshness: Record<string, string | null>;
  coverage: {
    as_of?: string;
    current_season?: string;
    leagues?: Record<string, any>;
    status?: string;
  };
  recent_runs: Array<{
    run_id: string;
    source: string;
    job?: string;
    status: string;
    started_at?: string | null;
    finished_at?: string | null;
    records_seen?: number;
    records_created?: number;
    records_updated?: number;
    records_rejected?: number;
    records_quarantined?: number;
    errors?: any;
  }>;
}

export interface JobRecord {
  id: number;
  job_id: string;
  job_type: string;
  source?: string | null;
  competition?: string | null;
  season?: string | null;
  requested_at?: string;
  started_at?: string;
  completed_at?: string;
  status: string;
  request_count?: number;
  success_count?: number;
  failure_count?: number;
  new_observations?: number;
  duplicate_observations?: number;
  new_matches?: number;
  updated_matches?: number;
  unresolved_identities?: number;
  conflicts?: number;
  duration_ms?: number;
  error_code?: string | null;
  dry_run?: boolean;
  trigger?: string;
  error_message?: string | null;
  details?: any;
}

export interface SchedulerDashboardResponse {
  as_of: string;
  sources: Record<string, {
    qualification: string;
    enabled: boolean;
    priority: number;
    health: SourceHealthInfo;
  }>;
  jobs: Record<string, {
    enabled: boolean;
    interval_seconds?: number;
    priority: number;
    last_run?: {
      job_id?: string | null;
      status?: string | null;
      completed_at?: string | null;
    } | null;
    running_count: number;
  }>;
  competitions: Record<string, {
    fixture_count: number;
    upcoming: number;
    latest_observation?: string | null;
  }>;
  locks: {
    total: number;
    active: number;
    stale: number;
  };
  recent_runs: Array<{
    job_id: string;
    job_type: string;
    competition?: string;
    status: string;
    duration_ms?: number;
    trigger?: string;
    completed_at?: string;
  }>;
}

export interface ReadyProbeResponse {
  status: 'ok' | 'degraded';
  checks: Record<string, string>;
}

export interface GateVerdict {
  passed: boolean;
  reasons: string[];
  status?: 'pass' | 'degraded' | 'fail';
  warnings?: string[];
}

export interface PreMatchReadinessResponse {
  match_id: number;
  competition: string;
  season: string;
  home_team_id: number;
  away_team_id: number;
  kickoff_at: string | null;
  cutoff: string;
  readiness_state: 'PREDICTION_READY' | 'READY_DEGRADED' | 'BLOCKED';
  eligible: boolean;
  mode: string;
  gate_verdicts: {
    gate1_structural: GateVerdict;
    gate2_reconciliation: GateVerdict;
    gate3_temporal: GateVerdict;
    gate4_features: GateVerdict;
  };
  blocking_reasons: string[];
  warnings: string[];
  missing_features: {
    core: string[];
    optional: string[];
  };
  evaluated_at: string;
  certificate?: {
    certificate_id: string;
    certificate_version: string;
    payload_hash: string;
    supersedes_certificate_id?: string | null;
    created_at?: string | null;
  };
}

export interface PreMatchReadinessSummaryResponse {
  season: string;
  operational_mode: string;
  provider_state: string;
  fixture_count: number;
  reconciled_count: number;
  temporally_valid_count: number;
  quality_passed_count: number;
  prediction_ready_count: number;
  ready_degraded_count: number;
  blocked_count: number;
  blocking_reasons: Record<string, number>;
  checked_at: string;
}
