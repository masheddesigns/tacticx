import React from 'react';
import { ShieldCheck, Server, Radio, Database, Activity, RefreshCw, CheckCircle2, XCircle, Globe, ShieldAlert } from 'lucide-react';
import { useSources, useAcquisitionStatus, useReadyProbe, useReadinessReport, usePreMatchReadinessSummary } from '../api/queries';
import { CurrentSeasonBanner } from '../components/dashboard/CurrentSeasonBanner';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';
import { Badge } from '../components/common/Badge';
import { formatDateTime } from '../lib/utils';

export const SystemStatusPage: React.FC = () => {
  const { data: sourcesData, isLoading: srcLoading, error: srcError, refetch: refetchSources } = useSources();
  const { data: acqData, isLoading: acqLoading, error: acqError, refetch: refetchAcq } = useAcquisitionStatus();
  const { data: readyProbe, refetch: refetchReady } = useReadyProbe();
  const { data: readinessData, refetch: refetchReadiness } = useReadinessReport();
  const { data: preMatchSummary, refetch: refetchPreMatch } = usePreMatchReadinessSummary();

  if (srcLoading || acqLoading) {
    return <LoadingSpinner label="Auditing Provider Health and Acquisition Systems..." />;
  }

  const sources = sourcesData?.sources || [];
  const recentRuns = acqData?.recent_runs || [];
  const coverage = acqData?.coverage || {};
  const readinessItems = readinessData?.items || [];
  const isEngineReady = readyProbe?.status === 'ok';

  const handleRefresh = () => {
    refetchSources();
    refetchAcq();
    refetchReady();
    refetchReadiness();
    refetchPreMatch();
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Server className="w-6 h-6 text-emerald-400" />
            <span>Sources & Provider Qualification Telemetry</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Real-time provider health, qualification tier auditing, and current-season fixture availability.
          </p>
        </div>

        <button
          onClick={handleRefresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-xs font-mono text-slate-300 hover:text-white transition-colors self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh Telemetry</span>
        </button>
      </div>

      {/* Engine Readiness Card */}
      <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono font-semibold text-slate-300 flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-400" />
            CORE ENGINE READINESS
          </span>
          <Badge variant={isEngineReady ? 'success' : 'warning'}>
            Status: {readyProbe?.status || 'Unknown'}
          </Badge>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
          <div className="p-3 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between">
            <span className="text-slate-400">Database Connection:</span>
            <span className="text-emerald-400 font-semibold">{readyProbe?.checks?.database || 'OK'}</span>
          </div>
          <div className="p-3 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between">
            <span className="text-slate-400">Cache Subsystem:</span>
            <span className="text-emerald-400 font-semibold">{readyProbe?.checks?.cache || 'OK'}</span>
          </div>
        </div>
      </div>

      {/* Current Season Availability Banner */}
      <CurrentSeasonBanner
        currentSeason={coverage.current_season || readinessData?.season || '2026/27'}
        readinessItems={readinessItems}
      />

      {/* Controlled Current-Season Competition Activation Matrix */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <Globe className="w-4 h-4 text-emerald-400" />
            <span>Controlled Current-Season Competition Activation</span>
          </h2>
          <span className="text-xs font-mono text-slate-400">
            5 Primary Leagues | Canonical Season {readinessData?.season || '2026/27'}
          </span>
        </div>

        <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden shadow-sm">
          {readinessItems.length === 0 ? (
            <div className="p-8 text-center text-xs font-mono text-slate-400">
              No readiness telemetry available for current season.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono border-collapse" aria-label="Current Season Readiness">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
                    <th className="p-2.5 text-left font-medium">Competition</th>
                    <th className="p-2.5 text-left font-medium">Candidate Provider</th>
                    <th className="p-2.5 text-center font-medium">Activation Status</th>
                    <th className="p-2.5 text-center font-medium">Qualification</th>
                    <th className="p-2.5 text-right font-medium">Fixtures</th>
                    <th className="p-2.5 text-center font-medium">Eligible</th>
                    <th className="p-2.5 text-left font-medium">Blocking Reasons</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {readinessItems.map((item: any) => {
                    const isAct = item.activation_status === 'ACTIVE';
                    const isQual = item.activation_status === 'QUALIFIED';
                    const isEligible = item.eligible_for_activation;
                    const badgeVariant = isAct ? 'success' : isQual ? 'info' : 'warning';

                    return (
                      <tr key={`${item.competition}-${item.provider}`} className="hover:bg-slate-900/40 transition-colors">
                        <td className="p-2.5 text-slate-200 font-bold">{item.competition}</td>
                        <td className="p-2.5 text-slate-400">{item.provider}</td>
                        <td className="p-2.5 text-center">
                          <Badge variant={badgeVariant} size="sm">
                            {item.activation_status}
                          </Badge>
                        </td>
                        <td className="p-2.5 text-center text-slate-300">
                          {item.qualification_level}
                        </td>
                        <td className="p-2.5 text-right text-slate-300">
                          {item.fixture_count !== null && item.fixture_count !== undefined ? item.fixture_count : 'N/A'}
                        </td>
                        <td className="p-2.5 text-center">
                          <span className={isEligible ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
                            {isEligible ? 'YES' : 'NO'}
                          </span>
                        </td>
                        <td className="p-2.5 text-slate-400 max-w-xs truncate" title={item.blocking_reasons?.join('; ')}>
                          {item.blocking_reasons?.length ? item.blocking_reasons.join('; ') : '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Phase 25: Pre-Match Data Quality & Readiness Gate Summary */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Pre-Match Data Quality & Readiness Gate Summary</span>
          </h2>
          <span className="text-xs font-mono text-slate-400">
            Phase 25 Gate Architecture | Contract: PREMATCH_CERTIFICATE_V1
          </span>
        </div>

        <div className="p-5 rounded-xl border border-surface-border bg-surface-card space-y-4 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Badge variant={preMatchSummary?.operational_mode === 'operational' ? 'success' : 'info'}>
                Mode: {preMatchSummary?.operational_mode || 'readiness_only'}
              </Badge>
              <span className="text-xs font-mono text-slate-400">
                Season: {preMatchSummary?.season || '2026/27'}
              </span>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Provider State: <strong className="text-slate-200">{preMatchSummary?.provider_state || 'UNAVAILABLE'}</strong>
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 text-center text-xs font-mono">
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Total Fixtures</span>
              <span className="text-base font-bold text-slate-100 mt-1 block">
                {preMatchSummary?.fixture_count ?? 0}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Reconciled (G1+G2)</span>
              <span className="text-base font-bold text-emerald-400 mt-1 block">
                {preMatchSummary?.reconciled_count ?? 0}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Temporal Valid (G3)</span>
              <span className="text-base font-bold text-emerald-400 mt-1 block">
                {preMatchSummary?.temporally_valid_count ?? 0}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Quality Passed (G4)</span>
              <span className="text-base font-bold text-emerald-400 mt-1 block">
                {preMatchSummary?.quality_passed_count ?? 0}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Prediction Ready</span>
              <span className="text-base font-bold text-emerald-400 mt-1 block">
                {preMatchSummary?.prediction_ready_count ?? 0}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Ready Degraded</span>
              <span className="text-base font-bold text-amber-400 mt-1 block">
                {preMatchSummary?.ready_degraded_count ?? 0}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-slate-400 block text-[10px]">Blocked</span>
              <span className="text-base font-bold text-rose-400 mt-1 block">
                {preMatchSummary?.blocked_count ?? 0}
              </span>
            </div>
          </div>


          {preMatchSummary?.fixture_count === 0 && (
            <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 flex items-start gap-2.5 text-xs font-mono text-slate-400">
              <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong className="text-slate-300">Readiness-Only Telemetry Active:</strong> Zero 2026/27 fixtures currently ingested. The pre-match data quality gate, cross-source reconciliation check, and immutable certificate generator are armed and operational, awaiting qualified current-season provider activation.
              </div>
            </div>
          )}

          {/* Phase 25.1 FIX 4/8: Per-competition provider activation context */}
          {preMatchSummary?.provider_activation_by_competition &&
            Object.keys(preMatchSummary.provider_activation_by_competition).length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] font-mono font-semibold text-slate-400 uppercase tracking-wider block">
                Provider Activation — Competition × Season Context
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                {Object.entries(preMatchSummary.provider_activation_by_competition).map(([comp, state]) => {
                  const isActive = state === 'ACTIVE';
                  const isQual = state === 'QUALIFIED';
                  const isDegraded = state === 'DEGRADED';
                  const stateColor = isActive
                    ? 'text-emerald-400 border-emerald-800'
                    : isQual
                    ? 'text-blue-400 border-blue-800'
                    : isDegraded
                    ? 'text-amber-400 border-amber-800'
                    : 'text-slate-500 border-slate-700';
                  return (
                    <div
                      key={comp}
                      className={`p-2 rounded bg-slate-900/60 border text-center text-[10px] font-mono ${stateColor}`}
                    >
                      <span className="text-slate-300 block font-bold">{comp}</span>
                      <span className="block mt-0.5">{state}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Phase 25.1 FIX 2/10: Duplicate detection state legend */}
          <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-800 text-[10px] font-mono text-slate-500 space-y-1">
            <span className="text-slate-400 font-semibold block">Duplicate Detection (Gate 2) — 4-State Logic:</span>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
              <span><span className="text-slate-300">NO_DUPLICATE</span> — no collision</span>
              <span><span className="text-amber-400">DUPLICATE_CANDIDATE</span> — proximity ±24h, warning only</span>
              <span><span className="text-rose-400">DUPLICATE_CONFIRMED</span> — same provider ID, blocking</span>
              <span><span className="text-rose-500">RESOLUTION_REQUIRED</span> — identity + proximity, blocking</span>
            </div>
          </div>
        </div>
      </section>


      {/* Registered Provider Registry */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <Radio className="w-4 h-4 text-blue-400" />
            <span>Registered Ingestion Providers</span>
          </h2>
          <span className="text-xs font-mono text-slate-400">{sources.length} adapters registered</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sources.map((src) => {
            const health = src.health || {};
            const isQualified = src.qualification_status === 'qualified';

            return (
              <div
                key={src.source_id}
                className="p-5 rounded-xl border border-surface-border bg-surface-card space-y-3 shadow-sm"
              >
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div>
                    <span className="font-bold text-sm text-slate-100 font-mono">{src.source_id}</span>
                    <span className="text-[11px] font-mono text-slate-400 block mt-0.5">
                      Tier: {src.tier || 'Standard'} | Priority: {src.priority}
                    </span>
                  </div>
                  <Badge variant={isQualified ? 'success' : 'default'} size="sm">
                    {src.qualification_status || 'Unqualified'}
                  </Badge>
                </div>

                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Health State:</span>
                    <span className="text-slate-200 font-bold">{health.state || 'unknown'}</span>
                  </div>

                  <div className="flex justify-between py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Consecutive Failures:</span>
                    <span className={health.consecutive_failures ? 'text-rose-400 font-bold' : 'text-slate-300'}>
                      {health.consecutive_failures ?? 0}
                    </span>
                  </div>

                  <div className="flex justify-between py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Quota Remaining:</span>
                    <span className="text-emerald-400">
                      {health.quota_remaining !== null && health.quota_remaining !== undefined
                        ? health.quota_remaining
                        : 'Unlimited / Local'}
                    </span>
                  </div>

                  <div className="flex justify-between py-1">
                    <span className="text-slate-400">Capabilities:</span>
                    <span className="text-slate-300 truncate max-w-[200px]" title={src.capabilities?.join(', ')}>
                      {src.capabilities?.join(', ') || 'Fixtures, Odds'}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Recent Acquisition Runs */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-purple-400" />
            <span>Recent Ingestion & Acquisition Executions</span>
          </h2>
          <span className="text-xs font-mono text-slate-400">{recentRuns.length} recent runs</span>
        </div>

        <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden shadow-sm">
          {recentRuns.length === 0 ? (
            <div className="p-8 text-center text-xs font-mono text-slate-400">
              No acquisition runs recorded in the audit log.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono border-collapse" aria-label="Acquisition Runs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
                    <th className="p-2.5 text-left font-medium">Run ID</th>
                    <th className="p-2.5 text-left font-medium">Source</th>
                    <th className="p-2.5 text-left font-medium">Job</th>
                    <th className="p-2.5 text-center font-medium">Status</th>
                    <th className="p-2.5 text-right font-medium">Records Seen</th>
                    <th className="p-2.5 text-right font-medium">Created</th>
                    <th className="p-2.5 text-right font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {recentRuns.map((r) => (
                    <tr key={r.run_id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="p-2.5 text-slate-300 font-semibold">{r.run_id}</td>
                      <td className="p-2.5 text-slate-200">{r.source}</td>
                      <td className="p-2.5 text-slate-400">{r.job || 'sync'}</td>
                      <td className="p-2.5 text-center">
                        <Badge
                          variant={
                            r.status === 'succeeded'
                              ? 'success'
                              : r.status === 'failed'
                              ? 'error'
                              : 'default'
                          }
                          size="sm"
                        >
                          {r.status}
                        </Badge>
                      </td>
                      <td className="p-2.5 text-right text-slate-300">{r.records_seen ?? 0}</td>
                      <td className="p-2.5 text-right text-emerald-400">{r.records_created ?? 0}</td>
                      <td className="p-2.5 text-right text-slate-300">{r.records_updated ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
