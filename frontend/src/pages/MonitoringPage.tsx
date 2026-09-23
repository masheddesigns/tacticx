import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Activity, AlertTriangle, CheckCircle2 } from 'lucide-react';
import {
  useEvaluationsSummary,
  useCalibration,
  useDrift,
  useMonitoringCoverage,
  useMonitoringAnomalies,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';
import { ModelPerformanceSection } from '../components/dashboard/ModelPerformanceSection';

const fmt = (v: any, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

export const MonitoringPage: React.FC = () => {
  const [competition, setCompetition] = useState<string>('');
  const [season, setSeason] = useState<string>('');

  const filters = {
    competition: competition || undefined,
    season: season || undefined,
  };

  const { data: summary, isLoading: summaryLoading, error: summaryError, refetch: refetchSummary } =
    useEvaluationsSummary(filters);
  const { data: calibration, refetch: refetchCal } = useCalibration();
  const { data: drift, refetch: refetchDrift } = useDrift(50);
  const { data: coverage, refetch: refetchCov } = useMonitoringCoverage(filters);
  const { data: anomalies, refetch: refetchAnom } = useMonitoringAnomalies();

  if (summaryLoading) {
    return <LoadingSpinner label="Loading production monitoring…" />;
  }

  if (summaryError) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <ErrorCard
          error={summaryError as Error}
          title="Monitoring Unavailable"
          onRetry={() => refetchSummary()}
        />
      </div>
    );
  }

  const handleRefresh = () => {
    refetchSummary();
    refetchCal();
    refetchDrift();
    refetchCov();
    refetchAnom();
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Activity className="w-6 h-6 text-teal-400" />
            <span>Production Monitoring</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Observability over immutable predictions & evaluations · measurement only, no model changes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={competition}
            onChange={(e) => setCompetition(e.target.value)}
            placeholder="Competition (e.g. EPL)"
            className="px-2 py-1.5 rounded-lg border border-slate-700 bg-slate-900 text-xs font-mono text-slate-200 w-44"
          />
          <input
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            placeholder="Season (e.g. 2024)"
            className="px-2 py-1.5 rounded-lg border border-slate-700 bg-slate-900 text-xs font-mono text-slate-200 w-32"
          />
          <button
            onClick={handleRefresh}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors"
            title="Refresh monitoring"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <ModelPerformanceSection summary={summary} calibration={calibration} drift={drift} />

      <section className="space-y-4">
        <h2 className="text-base font-semibold text-slate-100">Coverage Funnel</h2>
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card">
          {coverage ? (
            <div className="text-xs font-mono text-slate-300 space-y-1">
              <div>eligible {coverage.eligible_count} → ready {coverage.ready_count} → predicted{' '}
                {coverage.predicted_count} → completed {coverage.completed_count} → evaluated{' '}
                {coverage.evaluated_count}</div>
              <div className="text-slate-500">
                readiness {fmt(coverage.prediction_readiness_rate)} · coverage{' '}
                {fmt(coverage.prediction_coverage_rate)} · completion {fmt(coverage.completion_rate)} ·
                evaluated {fmt(coverage.evaluation_coverage_rate)}
              </div>
            </div>
          ) : (
            <div className="text-xs font-mono text-slate-500">No coverage data.</div>
          )}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400" />
          Anomalies
        </h2>
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card">
          {!anomalies || anomalies.anomaly_count === 0 ? (
            <div className="text-xs font-mono text-slate-400 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              No anomalies detected under current deterministic rules.
            </div>
          ) : (
            <ul className="space-y-2">
              {anomalies.anomalies.map((a: any) => (
                <li key={a.anomaly_id} className="text-xs font-mono text-slate-300">
                  <span className="text-slate-500">[{a.severity}]</span> {a.anomaly_type} · observed{' '}
                  {String(a.observed_value)} · n={a.sample_size}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <Link to="/system" className="text-xs font-mono text-slate-500 hover:text-slate-300">
        <ArrowLeft className="w-3.5 h-3.5 inline" /> Back to System
      </Link>
    </div>
  );
};
