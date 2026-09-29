import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, ApiError } from '../api/client';

describe('Centralized apiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('normalizes 404 match_not_found error from backend', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        code: 'match_not_found',
        message: 'unknown match: 999999',
      }),
    });

    try {
      await apiClient.getMatchIntelligence(999999);
      expect.fail('Expected error to be thrown');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe('match_not_found');
      expect(err.message).toBe('unknown match: 999999');
      expect(err.status).toBe(404);
    }
  });

  it('normalizes 400 prediction_unavailable error', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        code: 'prediction_unavailable',
        message: 'Insufficient historical sample',
      }),
    });

    try {
      await apiClient.getMatchIntelligence(101);
      expect.fail('Expected error');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe('prediction_unavailable');
      expect(err.message).toBe('Insufficient historical sample');
    }
  });

  it('handles request cancellation cleanly', async () => {
    const controller = new AbortController();
    global.fetch = vi.fn().mockImplementation(() => {
      const error = new Error('The operation was aborted');
      error.name = 'AbortError';
      return Promise.reject(error);
    });

    controller.abort();
    try {
      await apiClient.getMatches({ signal: controller.signal });
      expect.fail('Expected abort error');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe('request_aborted');
    }
  });

  it('formats query string correctly for matches', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [], meta: { page: 2, page_size: 10, total: 0 } }),
    });
    global.fetch = fetchMock;

    await apiClient.getMatches({
      league: 'EPL',
      status: 'FINISHED',
      page: 2,
      page_size: 10,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0];
    expect(calledUrl).toContain('league=EPL');
    expect(calledUrl).toContain('status=FINISHED');
    expect(calledUrl).toContain('page=2');
    expect(calledUrl).toContain('page_size=10');
  });
});

describe('Phase 26 prediction execution client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('posts execution with cutoff payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ executed: true, blocked: false, prediction_id: 'pred_1_x' }),
    });
    global.fetch = fetchMock;
    const res = await apiClient.executePrediction(7, { cutoff: '2024-09-01T12:00:00' });
    expect(res.prediction_id).toBe('pred_1_x');
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain('/matches/7/predictions');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body).cutoff).toBe('2024-09-01T12:00:00');
  });

  it('fetches prediction snapshots status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ match_id: 7, status: 'GENERATED', prediction_count: 1, snapshots: [] }),
    });
    const res = await apiClient.getPredictionSnapshots(7);
    expect(res.status).toBe('GENERATED');
    expect(res.prediction_count).toBe(1);
  });

  it('fetches a single prediction snapshot', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ prediction_id: 'pred_1_x', model_version: 'ensemble_v1-elo+poisson' }),
    });
    const res = await apiClient.getPredictionSnapshot('pred_1_x');
    expect(res.model_version).toBe('ensemble_v1-elo+poisson');
  });
});

describe('Phase 27 evaluation client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches match evaluation', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ match_id: 7, match_status: 'FINISHED', evaluation_count: 1, evaluations: [] }),
    });
    const res = await apiClient.getMatchEvaluation(7);
    expect(res.evaluation_count).toBe(1);
  });

  it('fetches evaluations summary with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ metrics: { sample_count: 5, accuracy_1x2: 0.6 } }),
    });
    global.fetch = fetchMock;
    const res = await apiClient.getEvaluationsSummary({ model_id: 'ensemble_v1-elo+poisson' });
    expect(res.metrics.sample_count).toBe(5);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/evaluations/summary');
    expect(url).toContain('model_id=ensemble_v1-elo%2Bpoisson');
  });

  it('fetches calibration and drift', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ n_bins: 10, sample_count: 2, per_outcome: {} }),
    });
    const cal = await apiClient.getCalibration();
    expect(cal.n_bins).toBe(10);
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ recent_sample: 2, sufficient_sample: false }),
    });
    const drift = await apiClient.getDrift({ recent_n: 50 });
    expect(drift.sufficient_sample).toBe(false);
  });
});

describe('Phase 28 monitoring client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches monitoring overview', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ evaluation_count: 3, accuracy: 0.66, drift_state: 'INSUFFICIENT_DATA' }),
    });
    const res = await apiClient.getMonitoringOverview();
    expect(res.evaluation_count).toBe(3);
  });

  it('fetches monitoring coverage with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ eligible_count: 7, evaluated_count: 1 }),
    });
    global.fetch = fetchMock;
    const res = await apiClient.getMonitoringCoverage({ competition: 'EPL' });
    expect(res.eligible_count).toBe(7);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/monitoring/coverage');
    expect(url).toContain('competition=EPL');
  });

  it('fetches monitoring anomalies', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ anomaly_count: 0, anomalies: [] }),
    });
    const res = await apiClient.getMonitoringAnomalies();
    expect(res.anomaly_count).toBe(0);
  });
});

describe('Phase 29 research client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches builtin candidates', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ builtin: ['baseline_repro', 'poisson_only'] }),
    });
    const res = await apiClient.getBuiltinCandidates();
    expect(res.builtin).toContain('baseline_repro');
  });

  it('runs a research experiment', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ experiment_id: 'exp_1', evidence_state: 'NO_CLEAR_DIFFERENCE' }),
    });
    global.fetch = fetchMock;
    const res = await apiClient.runResearchExperiment({ candidate_id: 'cand_1', dataset_id: 'ds_1' });
    expect(res.evidence_state).toBe('NO_CLEAR_DIFFERENCE');
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain('/research/experiments');
    expect(opts.method).toBe('POST');
  });

  it('fetches experiment comparison', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ experiment_id: 'exp_1', evidence_state: 'PASS' }),
    });
    const res = await apiClient.getExperimentComparison('exp_1');
    expect(res.experiment_id).toBe('exp_1');
  });
});

describe('Phase 30 governance client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches champion', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ role: 'CHAMPION', artifact: { model_id: 'ensemble_v1-elo+poisson' } }),
    });
    const res = await apiClient.getChampion();
    expect(res.artifact.model_id).toBe('ensemble_v1-elo+poisson');
  });

  it('fetches registry and audit', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ bindings: [] }),
    });
    const reg = await apiClient.getGovernanceRegistry();
    expect(reg.bindings).toEqual([]);
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ events: [] }),
    });
    const audit = await apiClient.getGovernanceAudit();
    expect(audit.events).toEqual([]);
  });
});

describe('Phase 32 shadow client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches shadow summary', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ shadow_executions: 2, shadow_evaluations: 1 }),
    });
    const res = await apiClient.getShadowSummary();
    expect(res.shadow_executions).toBe(2);
  });

  it('executes shadow with challenger', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ shadow_id: 'shdw_abc', cache_hit: false }),
    });
    global.fetch = fetchMock;
    const res = await apiClient.executeShadow(7, 'art_xyz');
    expect(res.shadow_id).toBe('shdw_abc');
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain('/shadow/execute/7');
    expect(opts.method).toBe('POST');
  });

  it('fetches shadow comparison', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ evaluated_pairs: 1, aggregate: {} }),
    });
    const res = await apiClient.getShadowComparison('art_xyz');
    expect(res.evaluated_pairs).toBe(1);
  });
});

describe('Phase 33 evidence client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches evidence status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ state: 'NO_DATA', champion_evaluations: 0, synthetic_observations: 0 }),
    });
    const res = await apiClient.getEvidenceStatus();
    expect(res.state).toBe('NO_DATA');
    expect(res.synthetic_observations).toBe(0);
  });

  it('fetches evidence snapshots', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ snapshots: [] }),
    });
    const res = await apiClient.getEvidenceSnapshots();
    expect(res.snapshots).toEqual([]);
  });

  it('fetches evidence compare', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ paired_count: 0, evidence_state: 'INSUFFICIENT_REAL_DATA' }),
    });
    const res = await apiClient.getEvidenceCompare('art_x');
    expect(res.evidence_state).toBe('INSUFFICIENT_REAL_DATA');
  });
});

describe('Phase 34 validation client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches validation status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ validation_count: 0, production_champion: 'ensemble_v1-elo+poisson' }),
    });
    const res = await apiClient.getValidationStatus();
    expect(res.production_champion).toBe('ensemble_v1-elo+poisson');
  });

  it('runs validation', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ validation_id: 'val_1', validation_state: 'INSUFFICIENT_DATA' }),
    });
    global.fetch = fetchMock;
    const res = await apiClient.runValidation({ candidate_artifact_id: 'art_x', evidence_snapshot_id: 'evd_y' });
    expect(res.validation_state).toBe('INSUFFICIENT_DATA');
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain('/candidate-validation/run');
    expect(opts.method).toBe('POST');
  });

  it('fetches validation rules', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ validation_id: 'val_1', validation_state: 'BLOCKED', rules: [] }),
    });
    const res = await apiClient.getValidation('val_1');
    expect(res.validation_id).toBe('val_1');
  });
});

describe('Phase 35 operations client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches soak summary', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ discovered: 0, paired: 0, exclusions: {} }),
    });
    const res = await apiClient.getSoakSummary();
    expect(res.paired).toBe(0);
  });
});
