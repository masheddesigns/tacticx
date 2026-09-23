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
