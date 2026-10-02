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
  preMatchReadiness: (matchId: number, options?: any) => ['preMatchReadiness', matchId, options],
  preMatchReadinessSummary: (params?: any) => ['preMatchReadinessSummary', params],
  predictionSnapshots: (matchId: number) => ['predictionSnapshots', matchId],
  predictionSnapshot: (predictionId: string) => ['predictionSnapshot', predictionId],
};

export function useMatches(params?: {
  league?: string;
  date?: string;
  team?: string;
  status?: string;
  page?: number;
  page_size?: number;
  sort_order?: 'asc' | 'desc';
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

export function useStatProjections(matchId: number) {
  return useQuery({
    queryKey: ['statProjections', matchId],
    queryFn: ({ signal }) => apiClient.getStatProjections(matchId, signal),
    enabled: !!matchId,
    staleTime: 60 * 1000,
  });
}

export function useMatchStatComparison(matchId: number) {
  return useQuery({
    queryKey: ['matchStatComparison', matchId],
    queryFn: ({ signal }) => apiClient.getMatchStatComparison(matchId, signal),
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

export function usePreMatchReadiness(
  matchId: number,
  options?: { cutoff?: string; mode?: string; persist?: boolean }
) {
  return useQuery({
    queryKey: QUERY_KEYS.preMatchReadiness(matchId, options),
    queryFn: ({ signal }) => apiClient.getPreMatchReadiness(matchId, { ...options, signal }),
    enabled: !!matchId,
    staleTime: 30 * 1000,
  });
}

export function usePreMatchReadinessSummary(params?: { season?: string }) {
  return useQuery({
    queryKey: QUERY_KEYS.preMatchReadinessSummary(params),
    queryFn: ({ signal }) => apiClient.getPreMatchReadinessSummary({ ...params, signal }),
    staleTime: 30 * 1000,
  });
}


export function usePredictionSnapshots(matchId: number) {
  return useQuery({
    queryKey: QUERY_KEYS.predictionSnapshots(matchId),
    queryFn: ({ signal }) => apiClient.getPredictionSnapshots(matchId, signal),
    enabled: !!matchId,
    staleTime: 30 * 1000,
  });
}

export function usePredictionSnapshot(predictionId: string) {
  return useQuery({
    queryKey: QUERY_KEYS.predictionSnapshot(predictionId),
    queryFn: ({ signal }) => apiClient.getPredictionSnapshot(predictionId, signal),
    enabled: !!predictionId,
    staleTime: 60 * 1000,
  });
}

export function useExecutePrediction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      matchId: number;
      cutoff: string;
      model_id?: string;
      certificate_id?: string;
    }) =>
      apiClient.executePrediction(args.matchId, {
        cutoff: args.cutoff,
        model_id: args.model_id,
        certificate_id: args.certificate_id,
      }),
    onSuccess: (data, vars) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.predictionSnapshots(vars.matchId) });
    },
  });
}

export function useMatchEvaluation(matchId: number) {
  return useQuery({
    queryKey: ['matchEvaluation', matchId],
    queryFn: ({ signal }) => apiClient.getMatchEvaluation(matchId, signal),
    enabled: !!matchId,
    staleTime: 60 * 1000,
  });
}

export function useEvaluationsSummary(params?: { model_id?: string; competition?: string; season?: string }) {
  return useQuery({
    queryKey: ['evaluationsSummary', params],
    queryFn: ({ signal }) => apiClient.getEvaluationsSummary({ ...params, signal }),
    staleTime: 60 * 1000,
  });
}

export function useCalibration(params?: { model_id?: string }) {
  return useQuery({
    queryKey: ['calibration', params],
    queryFn: ({ signal }) => apiClient.getCalibration({ ...params, signal }),
    staleTime: 60 * 1000,
  });
}

export function useDrift(recent_n?: number) {
  return useQuery({
    queryKey: ['drift', recent_n],
    queryFn: ({ signal }) => apiClient.getDrift({ recent_n, signal }),
    staleTime: 60 * 1000,
  });
}

export function useMonitoringCoverage(params?: { competition?: string; season?: string }) {
  return useQuery({
    queryKey: ['monitoringCoverage', params],
    queryFn: ({ signal }) => apiClient.getMonitoringCoverage({ ...params, signal }),
    staleTime: 60 * 1000,
  });
}

export function useMonitoringAnomalies() {
  return useQuery({
    queryKey: ['monitoringAnomalies'],
    queryFn: ({ signal }) => apiClient.getMonitoringAnomalies(signal),
    staleTime: 60 * 1000,
  });
}

export function useResearchCandidates() {
  return useQuery({
    queryKey: ['researchCandidates'],
    queryFn: ({ signal }) => apiClient.getResearchCandidates(signal),
    staleTime: 60 * 1000,
  });
}

export function useResearchCandidate(candidateId: string) {
  return useQuery({
    queryKey: ['researchCandidate', candidateId],
    queryFn: ({ signal }) => apiClient.getResearchCandidate(candidateId, signal),
    enabled: !!candidateId,
    staleTime: 60 * 1000,
  });
}

export function useResearchDatasets() {
  return useQuery({
    queryKey: ['researchDatasets'],
    queryFn: ({ signal }) => apiClient.getResearchDatasets(signal),
    staleTime: 60 * 1000,
  });
}

export function useResearchExperiments() {
  return useQuery({
    queryKey: ['researchExperiments'],
    queryFn: ({ signal }) => apiClient.getResearchExperiments(signal),
    staleTime: 60 * 1000,
  });
}

export function useResearchExperiment(experimentId: string) {
  return useQuery({
    queryKey: ['researchExperiment', experimentId],
    queryFn: ({ signal }) => apiClient.getResearchExperiment(experimentId, signal),
    enabled: !!experimentId,
    staleTime: 60 * 1000,
  });
}

export function useGovernanceRegistry() {
  return useQuery({
    queryKey: ['governanceRegistry'],
    queryFn: ({ signal }) => apiClient.getGovernanceRegistry(signal),
    staleTime: 60 * 1000,
  });
}

export function useChampion() {
  return useQuery({
    queryKey: ['champion'],
    queryFn: ({ signal }) => apiClient.getChampion(signal),
    staleTime: 60 * 1000,
  });
}

export function useArtifactStatus(artifactId: string) {
  return useQuery({
    queryKey: ['artifactStatus', artifactId],
    queryFn: ({ signal }) => apiClient.getArtifactStatus(artifactId, signal),
    enabled: !!artifactId,
    staleTime: 60 * 1000,
  });
}

export function usePromotionRequests() {
  return useQuery({
    queryKey: ['promotionRequests'],
    queryFn: ({ signal }) => apiClient.getPromotionRequests(signal),
    staleTime: 60 * 1000,
  });
}

export function useGovernanceAudit() {
  return useQuery({
    queryKey: ['governanceAudit'],
    queryFn: ({ signal }) => apiClient.getGovernanceAudit(signal),
    staleTime: 60 * 1000,
  });
}

export function useShadowSummary() {
  return useQuery({
    queryKey: ['shadowSummary'],
    queryFn: ({ signal }) => apiClient.getShadowSummary(signal),
    staleTime: 60 * 1000,
  });
}

export function useShadowChallengers() {
  return useQuery({
    queryKey: ['shadowChallengers'],
    queryFn: ({ signal }) => apiClient.getShadowChallengers(signal),
    staleTime: 60 * 1000,
  });
}

export function useShadowMatch(matchId: number) {
  return useQuery({
    queryKey: ['shadowMatch', matchId],
    queryFn: ({ signal }) => apiClient.getShadowMatch(matchId, signal),
    enabled: !!matchId,
    staleTime: 60 * 1000,
  });
}

export function useShadowComparison(challengerId: string) {
  return useQuery({
    queryKey: ['shadowComparison', challengerId],
    queryFn: ({ signal }) => apiClient.getShadowComparison(challengerId, signal),
    enabled: !!challengerId,
    staleTime: 60 * 1000,
  });
}

export function useEvidenceStatus() {
  return useQuery({
    queryKey: ['evidenceStatus'],
    queryFn: ({ signal }) => apiClient.getEvidenceStatus(signal),
    staleTime: 60 * 1000,
  });
}

export function useEvidenceSnapshots() {
  return useQuery({
    queryKey: ['evidenceSnapshots'],
    queryFn: ({ signal }) => apiClient.getEvidenceSnapshots(signal),
    staleTime: 60 * 1000,
  });
}

export function useEvidenceSnapshot(snapshotId: string) {
  return useQuery({
    queryKey: ['evidenceSnapshot', snapshotId],
    queryFn: ({ signal }) => apiClient.getEvidenceSnapshot(snapshotId, signal),
    enabled: !!snapshotId,
    staleTime: 60 * 1000,
  });
}

export function useValidationStatus() {
  return useQuery({
    queryKey: ['validationStatus'],
    queryFn: ({ signal }) => apiClient.getValidationStatus(signal),
    staleTime: 60 * 1000,
  });
}

export function useValidationConfig() {
  return useQuery({
    queryKey: ['validationConfig'],
    queryFn: ({ signal }) => apiClient.getValidationConfig(signal),
    staleTime: 300 * 1000,
  });
}

export function useValidationCandidates() {
  return useQuery({
    queryKey: ['validationCandidates'],
    queryFn: ({ signal }) => apiClient.getValidationCandidates(signal),
    staleTime: 60 * 1000,
  });
}

export function useValidationDetail(validationId: string) {
  return useQuery({
    queryKey: ['validationDetail', validationId],
    queryFn: ({ signal }) => apiClient.getValidation(validationId, signal),
    enabled: !!validationId,
    staleTime: 60 * 1000,
  });
}

export function useSoakSummary(params?: { competition?: string; season?: string }) {
  return useQuery({
    queryKey: ['soakSummary', params],
    queryFn: ({ signal }) => apiClient.getSoakSummary({ ...params, signal }),
    staleTime: 60 * 1000,
  });
}
