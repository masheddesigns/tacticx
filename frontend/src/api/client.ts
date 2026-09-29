/**
 * Centralized Typed TacticX API Client
 * Normalizes backend error responses (machine-readable codes) and prevents credential leaks.
 */
import {
  MatchListItem,
  PaginatedMatchesResponse,
  LeaguesResponse,
  MatchIntelligence,
  SourcesResponse,
  AcquisitionStatusResponse,
  SchedulerDashboardResponse,
  JobRecord,
  ReadyProbeResponse,
  PreMatchReadinessResponse,
  PreMatchReadinessSummaryResponse,
  PredictionExecutionResult,
  PredictionSnapshotsResponse,
  MatchEvaluationResponse,
  EvaluationRecord,
  EvaluationsSummaryResponse,
  CalibrationResponse,
  DriftResponse,
  ResearchCandidate,
  ResearchDataset,
  ResearchExperiment,
  GovernanceArtifact,
  ChampionView,
  PromotionRequest,
  GovernanceEvent,
  ShadowRecord,
  ShadowEvaluation,
  EvidenceCohort,
  EvidenceSnapshot,
  EvidenceStatus,
} from './types';

export class ApiError extends Error {
  public code: string;
  public status: number;
  public details?: any;

  constructor(message: string, code = 'unknown_error', status = 500, details?: any) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`;
  const headers = {
    'Accept': 'application/json',
    ...(options?.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options?.headers || {}),
  };

  try {
    const res = await fetch(url, { ...options, headers });
    
    if (!res.ok) {
      let errorJson: any = null;
      try {
        errorJson = await res.json();
      } catch {
        // Fallback for non-JSON error payloads
      }

      // Backend provides structured error codes e.g. {"code": "match_not_found", "message": "..."}
      // or FastAPI detail {"detail": "..."}
      const code = errorJson?.code || (res.status === 404 ? 'not_found' : 'http_error');
      const message = errorJson?.message || (typeof errorJson?.detail === 'string' ? errorJson.detail : `Request failed with status ${res.status}`);
      
      throw new ApiError(message, code, res.status, errorJson);
    }

    return (await res.json()) as T;
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (err.name === 'AbortError') {
      throw new ApiError('Request aborted', 'request_aborted', 0);
    }
    throw new ApiError(
      err.message || 'Unable to connect to TacticX backend',
      'network_error',
      0
    );
  }
}

export const apiClient = {
  // Matches
  getMatches: async (params?: {
    league?: string;
    date?: string;
    team?: string;
    status?: string;
    page?: number;
    page_size?: number;
    signal?: AbortSignal;
  }): Promise<PaginatedMatchesResponse> => {
    const query = new URLSearchParams();
    if (params?.league) query.set('league', params.league);
    if (params?.date) query.set('date', params.date);
    if (params?.team) query.set('team', params.team);
    if (params?.status) query.set('status', params.status);
    if (params?.page) query.set('page', String(params.page));
    if (params?.page_size) query.set('page_size', String(params.page_size));

    const qs = query.toString();
    return request<PaginatedMatchesResponse>(`/matches${qs ? `?${qs}` : ''}`, {
      signal: params?.signal,
    });
  },

  getCurrentMatches: async (params?: {
    competition?: string;
    status?: string;
    date?: string;
    eligible?: boolean;
    page?: number;
    page_size?: number;
    signal?: AbortSignal;
  }): Promise<PaginatedMatchesResponse> => {
    const query = new URLSearchParams();
    if (params?.competition) query.set('competition', params.competition);
    if (params?.status) query.set('status', params.status);
    if (params?.date) query.set('date', params.date);
    if (params?.eligible !== undefined) query.set('eligible', String(params.eligible));
    if (params?.page) query.set('page', String(params.page));
    if (params?.page_size) query.set('page_size', String(params.page_size));

    const qs = query.toString();
    return request<PaginatedMatchesResponse>(`/matches/current${qs ? `?${qs}` : ''}`, {
      signal: params?.signal,
    });
  },

  getMatch: async (matchId: number, signal?: AbortSignal): Promise<MatchListItem> => {
    return request<MatchListItem>(`/matches/${matchId}`, { signal });
  },

  getUpcomingMatches: async (hours = 24, signal?: AbortSignal): Promise<{ data: MatchListItem[] }> => {
    return request<{ data: MatchListItem[] }>(`/matches/upcoming?hours=${hours}`, { signal });
  },

  getLiveMatches: async (signal?: AbortSignal): Promise<{ data: MatchListItem[] }> => {
    return request<{ data: MatchListItem[] }>(`/matches/live`, { signal });
  },

  // Canonical Match Intelligence
  getMatchIntelligence: async (
    matchId: number,
    options?: {
      mode?: string;
      cutoff?: string;
      model?: string;
      seed?: number;
      response_mode?: 'standard' | 'compact';
      mirofish_scenario?: string;
      signal?: AbortSignal;
    }
  ): Promise<MatchIntelligence> => {
    const query = new URLSearchParams();
    if (options?.mode) query.set('mode', options.mode);
    if (options?.cutoff) query.set('cutoff', options.cutoff);
    if (options?.model) query.set('model', options.model);
    if (options?.seed !== undefined) query.set('seed', String(options.seed));
    if (options?.response_mode) query.set('response_mode', options.response_mode);
    if (options?.mirofish_scenario) query.set('mirofish_scenario', options.mirofish_scenario);

    const qs = query.toString();
    return request<MatchIntelligence>(`/matches/${matchId}/intelligence${qs ? `?${qs}` : ''}`, {
      signal: options?.signal,
    });
  },

  // Catalog
  getLeagues: async (signal?: AbortSignal): Promise<LeaguesResponse> => {
    return request<LeaguesResponse>('/leagues', { signal });
  },

  // Sources & Qualification
  getSources: async (signal?: AbortSignal): Promise<SourcesResponse> => {
    return request<SourcesResponse>('/sources', { signal });
  },

  getSourceStatus: async (sourceId: string, signal?: AbortSignal): Promise<any> => {
    return request<any>(`/sources/${encodeURIComponent(sourceId)}/status`, { signal });
  },

  getAcquisitionStatus: async (source?: string, signal?: AbortSignal): Promise<AcquisitionStatusResponse> => {
    const qs = source ? `?source=${encodeURIComponent(source)}` : '';
    return request<AcquisitionStatusResponse>(`/acquisition/status${qs}`, { signal });
  },

  // Jobs & Operations
  getJobDashboard: async (signal?: AbortSignal): Promise<SchedulerDashboardResponse> => {
    return request<SchedulerDashboardResponse>('/jobs/dashboard', { signal });
  },

  getJobs: async (params?: {
    job_type?: string;
    source?: string;
    competition?: string;
    status?: string;
    limit?: number;
    signal?: AbortSignal;
  }): Promise<JobRecord[]> => {
    const query = new URLSearchParams();
    if (params?.job_type) query.set('job_type', params.job_type);
    if (params?.source) query.set('source', params.source);
    if (params?.competition) query.set('competition', params.competition);
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));

    const qs = query.toString();
    return request<JobRecord[]>(`/jobs${qs ? `?${qs}` : ''}`, { signal: params?.signal });
  },

  getJobAlerts: async (signal?: AbortSignal): Promise<any[]> => {
    return request<any[]>('/jobs/alerts', { signal });
  },

  getJobAnomalies: async (signal?: AbortSignal): Promise<any[]> => {
    return request<any[]>('/jobs/anomalies', { signal });
  },

  getDueJobs: async (signal?: AbortSignal): Promise<any[]> => {
    return request<any[]>('/jobs/due', { signal });
  },

  cleanupLocks: async (): Promise<{ cleaned: number }> => {
    return request<{ cleaned: number }>('/jobs/locks/cleanup', { method: 'POST' });
  },

  // System Health
  getReadyProbe: async (signal?: AbortSignal): Promise<ReadyProbeResponse> => {
    return request<ReadyProbeResponse>('/ready', { signal });
  },

  // Controlled Current-Season Activation & Readiness
  getReadinessReport: async (params?: { season?: string; competition?: string; signal?: AbortSignal }): Promise<any> => {
    const query = new URLSearchParams();
    if (params?.season) query.set('season', params.season);
    if (params?.competition) query.set('competition', params.competition);
    const qs = query.toString();
    return request<any>(`/acquisition/readiness${qs ? `?${qs}` : ''}`, { signal: params?.signal });
  },

  // Phase 25: Pre-Match Readiness Gate & Quality Summary
  getPreMatchReadiness: async (
    matchId: number,
    options?: { cutoff?: string; mode?: string; persist?: boolean; signal?: AbortSignal }
  ): Promise<PreMatchReadinessResponse> => {
    const query = new URLSearchParams();
    if (options?.cutoff) query.set('cutoff', options.cutoff);
    if (options?.mode) query.set('mode', options.mode);
    if (options?.persist) query.set('persist', 'true');
    const qs = query.toString();
    return request<PreMatchReadinessResponse>(
      `/matches/${matchId}/pre-match-readiness${qs ? `?${qs}` : ''}`,
      { signal: options?.signal }
    );
  },

  getPreMatchReadinessSummary: async (params?: {
    season?: string;
    signal?: AbortSignal;
  }): Promise<PreMatchReadinessSummaryResponse> => {
    const query = new URLSearchParams();
    if (params?.season) query.set('season', params.season);
    const qs = query.toString();
    return request<PreMatchReadinessSummaryResponse>(
      `/matches/current/readiness-summary${qs ? `?${qs}` : ''}`,
      { signal: params?.signal }
    );
  },

  // Phase 26: Pre-Match Prediction Execution
  executePrediction: async (
    matchId: number,
    options?: { cutoff: string; model_id?: string; certificate_id?: string; with_intelligence?: boolean }
  ): Promise<PredictionExecutionResult> => {
    return request<PredictionExecutionResult>(`/matches/${matchId}/predictions`, {
      method: 'POST',
      body: JSON.stringify({
        cutoff: options?.cutoff,
        model_id: options?.model_id,
        certificate_id: options?.certificate_id,
        with_intelligence: options?.with_intelligence ?? false,
      }),
    });
  },

  getPredictionSnapshots: async (
    matchId: number,
    signal?: AbortSignal
  ): Promise<PredictionSnapshotsResponse> => {
    return request<PredictionSnapshotsResponse>(
      `/matches/${matchId}/prediction-snapshots`,
      { signal }
    );
  },

  getPredictionSnapshot: async (
    predictionId: string,
    signal?: AbortSignal
  ): Promise<PredictionExecutionResult> => {
    return request<PredictionExecutionResult>(
      `/prediction-snapshots/${predictionId}`,
      { signal }
    );
  },

  // Phase 27: Prediction Evaluation (read-only)
  getMatchEvaluation: async (
    matchId: number,
    signal?: AbortSignal
  ): Promise<MatchEvaluationResponse> => {
    return request<MatchEvaluationResponse>(
      `/matches/${matchId}/evaluation`,
      { signal }
    );
  },

  getPredictionEvaluation: async (
    predictionId: string,
    signal?: AbortSignal
  ): Promise<{ prediction_id: string; evaluation_count: number; evaluations: EvaluationRecord[] }> => {
    return request(
      `/prediction-snapshots/${predictionId}/evaluation`,
      { signal }
    );
  },

  getEvaluationsSummary: async (params?: {
    model_id?: string;
    model_version?: string;
    competition?: string;
    season?: string;
    signal?: AbortSignal;
  }): Promise<EvaluationsSummaryResponse> => {
    const query = new URLSearchParams();
    if (params?.model_id) query.set('model_id', params.model_id);
    if (params?.model_version) query.set('model_version', params.model_version);
    if (params?.competition) query.set('competition', params.competition);
    if (params?.season) query.set('season', params.season);
    const qs = query.toString();
    return request<EvaluationsSummaryResponse>(
      `/evaluations/summary${qs ? `?${qs}` : ''}`,
      { signal: params?.signal }
    );
  },

  getCalibration: async (params?: {
    model_id?: string;
    model_version?: string;
    signal?: AbortSignal;
  }): Promise<CalibrationResponse> => {
    const query = new URLSearchParams();
    if (params?.model_id) query.set('model_id', params.model_id);
    if (params?.model_version) query.set('model_version', params.model_version);
    const qs = query.toString();
    return request<CalibrationResponse>(
      `/evaluations/calibration${qs ? `?${qs}` : ''}`,
      { signal: params?.signal }
    );
  },

  getDrift: async (params?: {
    recent_n?: number;
    model_id?: string;
    signal?: AbortSignal;
  }): Promise<DriftResponse> => {
    const query = new URLSearchParams();
    if (params?.recent_n) query.set('recent_n', String(params.recent_n));
    if (params?.model_id) query.set('model_id', params.model_id);
    const qs = query.toString();
    return request<DriftResponse>(
      `/evaluations/drift${qs ? `?${qs}` : ''}`,
      { signal: params?.signal }
    );
  },

  // Phase 28: Production Monitoring (read-only)
  getMonitoringOverview: async (params?: {
    competition?: string;
    season?: string;
    signal?: AbortSignal;
  }): Promise<any> => {
    const query = new URLSearchParams();
    if (params?.competition) query.set('competition', params.competition);
    if (params?.season) query.set('season', params.season);
    const qs = query.toString();
    return request<any>(
      `/monitoring/overview${qs ? `?${qs}` : ''}`,
      { signal: params?.signal }
    );
  },

  getMonitoringCoverage: async (params?: {
    competition?: string;
    season?: string;
    signal?: AbortSignal;
  }): Promise<any> => {
    const query = new URLSearchParams();
    if (params?.competition) query.set('competition', params.competition);
    if (params?.season) query.set('season', params.season);
    const qs = query.toString();
    return request<any>(
      `/monitoring/coverage${qs ? `?${qs}` : ''}`,
      { signal: params?.signal }
    );
  },

  getMonitoringAnomalies: async (signal?: AbortSignal): Promise<any> => {
    return request<any>('/monitoring/anomalies', { signal });
  },

  // Phase 29: Controlled Research (execution guarded server-side)
  getBuiltinCandidates: async (signal?: AbortSignal): Promise<{ builtin: string[] }> => {
    return request<{ builtin: string[] }>('/research/candidates/builtin', { signal });
  },

  registerBuiltinCandidate: async (key: string): Promise<ResearchCandidate> => {
    return request<ResearchCandidate>(`/research/candidates/builtin/${key}`, { method: 'POST' });
  },

  getResearchCandidates: async (signal?: AbortSignal): Promise<{ candidates: ResearchCandidate[] }> => {
    return request<{ candidates: ResearchCandidate[] }>('/research/candidates', { signal });
  },

  getResearchCandidate: async (candidateId: string, signal?: AbortSignal): Promise<ResearchCandidate> => {
    return request<ResearchCandidate>(`/research/candidates/${candidateId}`, { signal });
  },

  buildResearchDataset: async (params?: {
    competitions?: string[];
    seasons?: string[];
  }): Promise<ResearchDataset> => {
    return request<ResearchDataset>('/research/datasets', {
      method: 'POST',
      body: JSON.stringify({
        competitions: params?.competitions ?? [],
        seasons: params?.seasons ?? [],
      }),
    });
  },

  getResearchDatasets: async (signal?: AbortSignal): Promise<{ datasets: ResearchDataset[] }> => {
    return request<{ datasets: ResearchDataset[] }>('/research/datasets', { signal });
  },

  runResearchExperiment: async (params: {
    candidate_id: string;
    dataset_id: string;
    seed?: number;
  }): Promise<ResearchExperiment> => {
    return request<ResearchExperiment>('/research/experiments', {
      method: 'POST',
      body: JSON.stringify({
        candidate_id: params.candidate_id,
        dataset_id: params.dataset_id,
        seed: params.seed ?? 7,
      }),
    });
  },

  getResearchExperiments: async (signal?: AbortSignal): Promise<{ experiments: ResearchExperiment[] }> => {
    return request<{ experiments: ResearchExperiment[] }>('/research/experiments', { signal });
  },

  getResearchExperiment: async (
    experimentId: string,
    signal?: AbortSignal
  ): Promise<ResearchExperiment> => {
    return request<ResearchExperiment>(`/research/experiments/${experimentId}`, { signal });
  },

  getExperimentComparison: async (
    experimentId: string,
    signal?: AbortSignal
  ): Promise<any> => {
    return request<any>(`/research/experiments/${experimentId}/comparison`, { signal });
  },

  // Phase 30: Model Governance (mutations guarded server-side)
  getGovernanceRegistry: async (signal?: AbortSignal): Promise<{ bindings: any[] }> => {
    return request<{ bindings: any[] }>('/model-governance/registry', { signal });
  },

  getChampion: async (signal?: AbortSignal): Promise<ChampionView> => {
    return request<ChampionView>('/model-governance/champion', { signal });
  },

  getGovernanceArtifact: async (
    artifactId: string,
    signal?: AbortSignal
  ): Promise<GovernanceArtifact> => {
    return request<GovernanceArtifact>(`/model-governance/artifacts/${artifactId}`, { signal });
  },

  getArtifactStatus: async (artifactId: string, signal?: AbortSignal): Promise<any> => {
    return request<any>(`/model-governance/status/${artifactId}`, { signal });
  },

  getPromotionRequests: async (signal?: AbortSignal): Promise<{ requests: PromotionRequest[] }> => {
    return request<{ requests: PromotionRequest[] }>('/model-governance/promotion-requests', { signal });
  },

  getGovernanceAudit: async (signal?: AbortSignal): Promise<{ events: GovernanceEvent[] }> => {
    return request<{ events: GovernanceEvent[] }>('/model-governance/audit', { signal });
  },

  // Phase 32: Champion/challenger shadow (execution guarded server-side)
  getShadowSummary: async (signal?: AbortSignal): Promise<any> => {
    return request<any>('/shadow/summary', { signal });
  },

  getShadowChallengers: async (signal?: AbortSignal): Promise<{ challengers: string[] }> => {
    return request<{ challengers: string[] }>('/shadow/challengers', { signal });
  },

  getShadowMatches: async (signal?: AbortSignal): Promise<any> => {
    return request<any>('/shadow/matches', { signal });
  },

  getShadowMatch: async (matchId: number, signal?: AbortSignal): Promise<{ match_id: number; shadow_count: number; shadows: ShadowRecord[] }> => {
    return request(`/shadow/matches/${matchId}`, { signal });
  },

  getShadowEvaluations: async (signal?: AbortSignal): Promise<{ evaluation_count: number; evaluations: ShadowEvaluation[] }> => {
    return request('/shadow/evaluations', { signal });
  },

  getShadowComparison: async (challengerId: string, signal?: AbortSignal): Promise<any> => {
    return request<any>(`/shadow/comparison/${challengerId}`, { signal });
  },

  executeShadow: async (matchId: number, challengerArtifactId: string): Promise<ShadowRecord> => {
    return request<ShadowRecord>(`/shadow/execute/${matchId}`, {
      method: 'POST',
      body: JSON.stringify({ match_id: matchId, challenger_artifact_id: challengerArtifactId }),
    });
  },

  // Phase 33: Real-world performance evidence (generation guarded server-side)
  getEvidenceStatus: async (signal?: AbortSignal): Promise<EvidenceStatus> => {
    return request<EvidenceStatus>('/evidence/status', { signal });
  },

  getEvidenceCohorts: async (signal?: AbortSignal): Promise<{ cohorts: EvidenceCohort[] }> => {
    return request<{ cohorts: EvidenceCohort[] }>('/evidence/cohorts', { signal });
  },

  getEvidenceSnapshots: async (signal?: AbortSignal): Promise<{ snapshots: EvidenceSnapshot[] }> => {
    return request<{ snapshots: EvidenceSnapshot[] }>('/evidence/snapshots', { signal });
  },

  getEvidenceSnapshot: async (snapshotId: string, signal?: AbortSignal): Promise<EvidenceSnapshot> => {
    return request<EvidenceSnapshot>(`/evidence/snapshots/${snapshotId}`, { signal });
  },

  getEvidenceCompare: async (challengerId: string, signal?: AbortSignal): Promise<any> => {
    return request<any>(`/evidence/compare/${challengerId}`, { signal });
  },
};
