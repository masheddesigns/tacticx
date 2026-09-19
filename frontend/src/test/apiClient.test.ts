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
