import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';

export const QUERY_KEYS = {
  matches: (params?: any) => ['matches', params],
  currentMatches: (params?: any) => ['currentMatches', params],
  match: (id: number) => ['match', id],
  upcomingMatches: (hours?: number) => ['upcomingMatches', hours],
  liveMatches: () => ['liveMatches'],
  intelligence: (id: number, opts?: any) => ['intelligence', id, opts],
  leagues: () => ['leagues'],
  sources: () => ['sources'],
  sourceStatus: (id: string) => ['sourceStatus', id],
  acquisitionStatus: (source?: string) => ['acquisitionStatus', source],
  jobDashboard: () => ['jobDashboard'],
  jobs: (params?: any) => ['jobs', params],
  jobAlerts: () => ['jobAlerts'],
  jobAnomalies: () => ['jobAnomalies'],
  jobDue: () => ['jobDue'],
  readyProbe: () => ['readyProbe'],
  readinessReport: (params?: any) => ['readinessReport', params],
};

export function useMatches(params?: {
  league?: string;
  date?: string;
  team?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: QUERY_KEYS.matches(params),
    queryFn: ({ signal }) => apiClient.getMatches({ ...params, signal }),
    staleTime: 30 * 1000,
  });
}

export function useCurrentMatches(params?: {
  competition?: string;
  status?: string;
  date?: string;
  eligible?: boolean;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: QUERY_KEYS.currentMatches(params),
    queryFn: ({ signal }) => apiClient.getCurrentMatches({ ...params, signal }),
    staleTime: 30 * 1000,
  });
}

export function useMatch(matchId: number) {
  return useQuery({
    queryKey: QUERY_KEYS.match(matchId),
    queryFn: ({ signal }) => apiClient.getMatch(matchId, signal),
    enabled: !!matchId,
    staleTime: 60 * 1000,
  });
}

export function useUpcomingMatches(hours = 24) {
  return useQuery({
    queryKey: QUERY_KEYS.upcomingMatches(hours),
    queryFn: ({ signal }) => apiClient.getUpcomingMatches(hours, signal),
    staleTime: 60 * 1000,
  });
}

export function useLiveMatches() {
  return useQuery({
    queryKey: QUERY_KEYS.liveMatches(),
    queryFn: ({ signal }) => apiClient.getLiveMatches(signal),
    refetchInterval: 30 * 1000,
    staleTime: 15 * 1000,
  });
}

export function useMatchIntelligence(
  matchId: number,
  options?: {
    mode?: string;
    cutoff?: string;
    model?: string;
    seed?: number;
    response_mode?: 'standard' | 'compact';
    mirofish_scenario?: string;
  }
) {
  return useQuery({
    queryKey: QUERY_KEYS.intelligence(matchId, options),
    queryFn: ({ signal }) => apiClient.getMatchIntelligence(matchId, { ...options, signal }),
    enabled: !!matchId,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useLeagues() {
  return useQuery({
    queryKey: QUERY_KEYS.leagues(),
    queryFn: ({ signal }) => apiClient.getLeagues(signal),
    staleTime: 10 * 60 * 1000,
  });
}

export function useSources() {
  return useQuery({
    queryKey: QUERY_KEYS.sources(),
    queryFn: ({ signal }) => apiClient.getSources(signal),
    staleTime: 30 * 1000,
  });
}

export function useSourceStatus(sourceId: string) {
  return useQuery({
    queryKey: QUERY_KEYS.sourceStatus(sourceId),
    queryFn: ({ signal }) => apiClient.getSourceStatus(sourceId, signal),
    enabled: !!sourceId,
    staleTime: 30 * 1000,
  });
}

export function useAcquisitionStatus(source?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.acquisitionStatus(source),
    queryFn: ({ signal }) => apiClient.getAcquisitionStatus(source, signal),
    staleTime: 20 * 1000,
  });
}

export function useJobDashboard() {
  return useQuery({
    queryKey: QUERY_KEYS.jobDashboard(),
    queryFn: ({ signal }) => apiClient.getJobDashboard(signal),
    staleTime: 15 * 1000,
  });
}

export function useJobs(params?: {
  job_type?: string;
  source?: string;
  competition?: string;
  status?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: QUERY_KEYS.jobs(params),
    queryFn: ({ signal }) => apiClient.getJobs({ ...params, signal }),
    staleTime: 15 * 1000,
  });
}

export function useJobAlerts() {
  return useQuery({
    queryKey: QUERY_KEYS.jobAlerts(),
    queryFn: ({ signal }) => apiClient.getJobAlerts(signal),
    staleTime: 20 * 1000,
  });
}

export function useJobAnomalies() {
  return useQuery({
    queryKey: QUERY_KEYS.jobAnomalies(),
    queryFn: ({ signal }) => apiClient.getJobAnomalies(signal),
    staleTime: 20 * 1000,
  });
}

export function useJobDue() {
  return useQuery({
    queryKey: QUERY_KEYS.jobDue(),
    queryFn: ({ signal }) => apiClient.getDueJobs(signal),
    staleTime: 20 * 1000,
  });
}

export function useReadyProbe() {
  return useQuery({
    queryKey: QUERY_KEYS.readyProbe(),
    queryFn: ({ signal }) => apiClient.getReadyProbe(signal),
    staleTime: 15 * 1000,
  });
}

export function useCleanupLocks() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.cleanupLocks(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.jobDashboard() });
    },
  });
}

export function useReadinessReport(params?: { season?: string; competition?: string }) {
  return useQuery({
    queryKey: QUERY_KEYS.readinessReport(params),
    queryFn: ({ signal }) => apiClient.getReadinessReport({ ...params, signal }),
    staleTime: 30 * 1000,
  });
}

