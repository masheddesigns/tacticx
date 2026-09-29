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
  /** Global provider state (ACTIVE if any competition is ACTIVE for this season) */
  provider_state: string;
  /** Per-competition provider activation state, scoped to provider × competition × season (Phase 25.1) */
  provider_activation_by_competition: Record<string, string>;
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

/** 4-state duplicate detection result (Phase 25.1 FIX 2) */
export type DuplicateDetectionState =
  | 'NO_DUPLICATE'
  | 'DUPLICATE_CANDIDATE'      // proximity only — warning, not blocking
  | 'DUPLICATE_CONFIRMED'      // exact provider+provider_match_id collision — blocking
  | 'DUPLICATE_RESOLUTION_REQUIRED';  // both conditions — blocking

/** Phase 26: pre-match prediction execution status */
export type PredictionExecutionStatus =
  | 'NOT_GENERATED'
  | 'GENERATED'
  | 'DEGRADED'
  | 'BLOCKED';

export interface PredictionSnapshotSummary {
  prediction_id: string;
  prediction_version: number;
  model_id: string;
  model_version: string;
  cutoff_time?: string | null;
  readiness_state?: string | null;
  prediction_hash: string;
  created_at?: string | null;
}

export interface PredictionExecutionResult {
  executed?: boolean;
  blocked?: boolean;
  code?: string;
  reason?: string;
  details?: any;
  cache_hit?: boolean;
  prediction_id?: string;
  match_id?: number;
  prediction_version?: number;
  model_id?: string;
  model_version?: string;
  prediction_mode?: string;
  cutoff_time?: string | null;
  kickoff_time?: string | null;
  readiness_certificate_id?: string | null;
  readiness_certificate_hash?: string | null;
  readiness_state?: string | null;
  feature_snapshot_id?: string | null;
  feature_snapshot_hash?: string | null;
  prediction_payload?: any;
  prediction_hash?: string | null;
  provenance?: any;
  created_at?: string | null;
}

export interface PredictionSnapshotsResponse {
  match_id: number;
  status: PredictionExecutionStatus;
  prediction_count: number;
  latest?: PredictionExecutionResult | null;
  latest_certificate_id?: string | null;
  latest_readiness_state?: string | null;
  snapshots: PredictionSnapshotSummary[];
}

/** Phase 27: prediction evaluation */
export interface EvaluationMetrics {
  actual_result?: string;
  actual_home_goals?: number;
  actual_away_goals?: number;
  accuracy_1x2?: number;
  log_loss_1x2?: number;
  brier_1x2?: number;
  home_goal_error?: number;
  away_goal_error?: number;
  goal_mae?: number;
  total_goal_error?: number;
  ou_1_5_accuracy?: number;
  ou_2_5_accuracy?: number;
  ou_3_5_accuracy?: number;
  btts_accuracy?: number;
  exact_score_hit?: number;
  [key: string]: any;
}

export interface OutcomeSnapshot {
  outcome_id: string;
  match_id: number;
  final_home_goals: number;
  final_away_goals: number;
  final_result: string;
  status: string;
  outcome_hash: string;
  supersedes_outcome_id?: string | null;
  created_at?: string | null;
}

export interface EvaluationRecord {
  evaluation_id: string;
  prediction_id: string;
  prediction_hash: string;
  outcome_snapshot_id: string;
  outcome_hash: string;
  model_id: string;
  model_version: string;
  actual_result: string;
  actual_home_goals: number;
  actual_away_goals: number;
  metrics: EvaluationMetrics;
  evaluation_version: number;
  created_at?: string | null;
}

export interface MatchEvaluationResponse {
  match_id: number;
  match_status: string;
  final_score: { home?: number | null; away?: number | null };
  outcome_eligible: boolean;
  outcome_eligibility_code: string;
  outcome?: OutcomeSnapshot | null;
  prediction_count: number;
  evaluation_count: number;
  evaluations: EvaluationRecord[];
}

export interface EvaluationsSummaryResponse {
  filters: Record<string, any>;
  evaluation_period: { from?: string | null; to?: string | null };
  metrics: Record<string, any>;
}

export interface CalibrationResponse {
  n_bins: number;
  sample_count: number;
  filters: Record<string, any>;
  per_outcome: Record<string, any>;
}

export interface DriftResponse {
  recent_n_requested: number;
  recent_sample: number;
  baseline_sample: number;
  sufficient_sample: boolean;
  min_sample: number;
  recent_means: Record<string, any>;
  baseline_means: Record<string, any>;
  differences_recent_minus_baseline: Record<string, any>;
}

/** Phase 29: controlled research pipeline */
export interface ResearchCandidate {
  candidate_id: string;
  name: string;
  version: string;
  description?: string;
  hypothesis?: string;
  feature_set?: any;
  model_family?: string;
  hyperparameters?: any;
  declared_inputs?: any;
  code_hash?: string;
  status: string;
  supersedes_candidate_id?: string | null;
  created_at?: string | null;
}

export interface ResearchDataset {
  dataset_id: string;
  dataset_version: string;
  feature_version: string;
  cutoff_policy: string;
  observation_count: number;
  train_period?: any;
  validation_period?: any;
  test_period?: any;
  dataset_hash: string;
  created_at?: string | null;
}

export interface ResearchExperiment {
  experiment_id: string;
  candidate_id: string;
  candidate_version: string;
  dataset_id: string;
  dataset_hash: string;
  baseline_model_id: string;
  baseline_metrics?: any;
  candidate_metrics?: any;
  comparison?: any;
  uncertainty?: any;
  calibration?: any;
  leakage_status: string;
  evidence_state: string;
  reproducibility?: any;
  execution_metadata?: any;
  result_hash: string;
  rerun?: boolean;
  created_at?: string | null;
}

/** Phase 30: model governance */
export interface GovernanceArtifact {
  artifact_id: string;
  model_id: string;
  model_version: string;
  candidate_id?: string | null;
  experiment_id?: string | null;
  dataset_id?: string | null;
  dataset_hash?: string | null;
  config_fingerprint?: any;
  feature_contract?: string;
  prediction_mode?: string;
  lifecycle_state: string;
  artifact_hash: string;
  created_at?: string | null;
}

export interface ChampionView {
  role: string;
  competition?: string | null;
  season?: string | null;
  prediction_mode: string;
  artifact: GovernanceArtifact;
  registry_id: number;
  bound_at?: string | null;
}

export interface PromotionRequest {
  request_id: string;
  candidate_artifact_id: string;
  validation_id: string;
  champion_artifact_id: string;
  deployment_mode: string;
  requester: string;
  reason: string;
  state: string;
  created_at?: string | null;
}

export interface GovernanceEvent {
  event_id: string;
  artifact_id?: string | null;
  from_state: string;
  to_state: string;
  actor: string;
  reason: string;
  created_at?: string | null;
}

/** Phase 32: champion/challenger shadow */
export interface ShadowRecord {
  shadow_id: string;
  match_id: number;
  challenger_artifact_id: string;
  champion_artifact_id: string;
  cutoff?: string | null;
  feature_snapshot_id?: string | null;
  feature_snapshot_hash?: string | null;
  production_prediction_id?: string | null;
  shadow_execution_key?: string | null;
  evaluation_state?: string | null;
  champion_output_hash?: string | null;
  challenger_output_hash?: string | null;
  created_at?: string | null;
}

export interface ShadowEvaluation {
  evaluation_id: string;
  shadow_id: string;
  match_id: number;
  challenger_artifact_id: string;
  champion_artifact_id: string;
  outcome_snapshot_id: string;
  outcome_hash: string;
  champion_metrics?: any;
  challenger_metrics?: any;
  differences?: any;
  created_at?: string | null;
}

/** Phase 33: real-world performance evidence */
export interface EvidenceCohort {
  cohort_id: string;
  champion_artifact_id?: string | null;
  challenger_artifact_id?: string | null;
  competitions?: any;
  seasons?: any;
  cohort_hash: string;
  created_at?: string | null;
}

export interface EvidenceSnapshot {
  snapshot_id: string;
  cohort_id: string;
  cohort_hash: string;
  calculation_version: string;
  observation_count: number;
  paired_count: number;
  excluded_count: number;
  champion_metrics?: any;
  challenger_metrics?: any;
  differences?: any;
  uncertainty?: any;
  calibration?: any;
  data_quality?: any;
  temporal_audit?: any;
  evidence_state: string;
  snapshot_hash: string;
  rerun?: boolean;
  created_at?: string | null;
}

export interface EvidenceStatus {
  state: string;
  champion_evaluations: number;
  challenger_evaluations: number;
  paired_observations: number;
  real_shadow_predictions: number;
  synthetic_observations: number;
  evidence_snapshots: number;
}

/** Phase 34: controlled candidate validation */
export interface ValidationRule {
  rule_id: string;
  state: string;
  result: boolean;
  explanation: string;
  measured_value?: any;
  required_value?: any;
  evidence_reference?: string | null;
}

export interface CandidateValidation {
  validation_id: string;
  candidate_artifact_id: string;
  champion_artifact_id: string;
  evidence_snapshot_id: string;
  evidence_snapshot_hash: string;
  validation_config_id: string;
  validation_config_version: string;
  validation_state: string;
  evidence_state?: string | null;
  rule_results?: any;
  performance_summary?: any;
  uncertainty_summary?: any;
  data_quality_summary?: any;
  temporal_summary?: any;
  compatibility_summary?: any;
  operational_summary?: any;
  blocking_reasons?: any;
  warnings?: any;
  validation_hash: string;
  rerun?: boolean;
  created_at?: string | null;
}
