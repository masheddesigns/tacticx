import React, { useState } from 'react';
import { Terminal, Lock, AlertTriangle, AlertCircle, RefreshCw, CheckCircle, ShieldAlert } from 'lucide-react';
import {
  useJobs,
  useJobDashboard,
  useJobAlerts,
  useJobAnomalies,
  useJobDue,
  useCleanupLocks,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';
import { Badge } from '../components/common/Badge';

export const OperationsPage: React.FC = () => {
  const [jobStatusFilter, setJobStatusFilter] = useState<string>('');
  const [jobTypeFilter, setJobTypeFilter] = useState<string>('');

  const { data: dashboard, isLoading: dashLoading, refetch: refetchDash } = useJobDashboard();
  const { data: jobs, isLoading: jobsLoading, refetch: refetchJobs } = useJobs({
    status: jobStatusFilter || undefined,
    job_type: jobTypeFilter || undefined,
    limit: 50,
  });
  const { data: alerts, refetch: refetchAlerts } = useJobAlerts();
  const { data: anomalies, refetch: refetchAnomalies } = useJobAnomalies();
  const { data: dueJobs, refetch: refetchDue } = useJobDue();

  const cleanupMutation = useCleanupLocks();

  const handleRefresh = () => {
    refetchDash();
    refetchJobs();
    refetchAlerts();
    refetchAnomalies();
    refetchDue();
  };

  const locks = dashboard?.locks || { total: 0, active: 0, stale: 0 };
  const alertList = alerts || [];
  const anomalyList = anomalies || [];
  const dueList = dueJobs || [];
  const jobRecords = jobs || [];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Terminal className="w-6 h-6 text-emerald-400" />
            <span>Scheduler Operations & Job Audit</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Production recurring scheduler telemetry, distributed locks, anomaly auditing, and alert status.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-xs font-mono text-slate-300 hover:text-white transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh Telemetry</span>
          </button>
        </div>
      </div>

      {/* Operational Metrics: Locks & Alerts */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Active & Stale Locks */}
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-slate-400" />
              Scheduler Locks
            </span>
            {locks.stale > 0 && (
              <button
                onClick={() => cleanupMutation.mutate()}
                disabled={cleanupMutation.isPending}
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-900/60 text-amber-300 border border-amber-800 hover:bg-amber-800 transition-colors"
              >
                {cleanupMutation.isPending ? 'Cleaning...' : 'Clean Stale'}
              </button>
            )}
          </div>
          <div className="text-xl font-mono font-bold text-slate-100">
            {locks.active} Active <span className="text-slate-500 font-normal">/ {locks.total} Total</span>
          </div>
          <span className="text-[11px] font-mono text-slate-400 block">
            Stale expired locks: {locks.stale}
          </span>
        </div>

        {/* Operational Alerts */}
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-2">
          <span className="text-xs font-mono text-slate-400 flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
            Active Operational Alerts
          </span>
          <div className="text-xl font-mono font-bold text-slate-100">
            {alertList.length} Conditions
          </div>
          <span className="text-[11px] font-mono text-slate-400 block">
            {alertList.length === 0 ? 'All pipelines nominal' : 'Attention required'}
          </span>
        </div>

        {/* Detected Anomalies */}
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-2">
          <span className="text-xs font-mono text-slate-400 flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 text-blue-400" />
            Ingestion Anomalies
          </span>
          <div className="text-xl font-mono font-bold text-slate-100">
            {anomalyList.length} Detected
          </div>
          <span className="text-[11px] font-mono text-slate-400 block">
            Cadence & drift monitoring
          </span>
        </div>
      </div>

      {/* Filter Bar for Job Records */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl border border-surface-border bg-surface-card text-xs font-mono">
        <div className="flex items-center gap-3">
          <span className="text-slate-400">Filter Jobs:</span>
          <select
            value={jobStatusFilter}
            onChange={(e) => setJobStatusFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
          >
            <option value="">All Statuses</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="running">Running</option>
            <option value="partial">Partial</option>
          </select>
        </div>

        <span className="text-slate-400">{jobRecords.length} records shown</span>
      </div>

      {/* Jobs Audit Table */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-100 font-mono">
          RECENT SCHEDULER EXECUTION LOGS
        </h2>

        <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden shadow-sm">
          {jobsLoading ? (
            <LoadingSpinner label="Auditing execution logs..." />
          ) : jobRecords.length === 0 ? (
            <div className="p-8 text-center text-xs font-mono text-slate-400">
              No recent jobs matching criteria.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono border-collapse" aria-label="Job Execution Logs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
                    <th className="p-2.5 text-left font-medium">Job ID</th>
                    <th className="p-2.5 text-left font-medium">Type</th>
                    <th className="p-2.5 text-left font-medium">Source / League</th>
                    <th className="p-2.5 text-center font-medium">Status</th>
                    <th className="p-2.5 text-right font-medium">Duration</th>
                    <th className="p-2.5 text-right font-medium">New Obs</th>
                    <th className="p-2.5 text-right font-medium">Conflicts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {jobRecords.map((j) => (
                    <tr key={j.id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="p-2.5 text-slate-300 font-semibold">{j.job_id}</td>
                      <td className="p-2.5 text-slate-200">{j.job_type}</td>
                      <td className="p-2.5 text-slate-400">
                        {j.source || j.competition || 'System'}
                      </td>
                      <td className="p-2.5 text-center">
                        <Badge
                          variant={
                            j.status === 'succeeded'
                              ? 'success'
                              : j.status === 'failed'
                              ? 'error'
                              : 'default'
                          }
                          size="sm"
                        >
                          {j.status}
                        </Badge>
                      </td>
                      <td className="p-2.5 text-right text-slate-400">{j.duration_ms ?? 0} ms</td>
                      <td className="p-2.5 text-right text-emerald-400">{j.new_observations ?? 0}</td>
                      <td className="p-2.5 text-right text-slate-400">{j.conflicts ?? 0}</td>
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
