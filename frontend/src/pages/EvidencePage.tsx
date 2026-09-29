import React, { useState } from 'react';
import { Scale, RefreshCw, AlertCircle } from 'lucide-react';
import {
  useEvidenceStatus,
  useEvidenceSnapshots,
  useEvidenceSnapshot,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

const fmt = (v: any, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

const STATE_TONE: Record<string, string> = {
  NO_DATA: 'text-slate-400',
  INSUFFICIENT_REAL_DATA: 'text-amber-400',
  DESCRIPTIVE_ONLY: 'text-sky-400',
  INCONCLUSIVE: 'text-slate-300',
  SUPPORTED_DIFFERENCE: 'text-violet-400',
  CONFLICTING_EVIDENCE: 'text-orange-400',
  INVALID: 'text-red-400',
};

export const EvidencePage: React.FC = () => {
  const [snapshotId, setSnapshotId] = useState<string>('');

  const { data: status, isLoading, error, refetch } = useEvidenceStatus();
  const { data: snapshots } = useEvidenceSnapshots();
  const { data: detail } = useEvidenceSnapshot(snapshotId);

  if (isLoading) {
    return <LoadingSpinner label="Loading real-world evidence…" />;
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <ErrorCard error={error as Error} title="Evidence Unavailable" onRetry={() => refetch()} />
      </div>
    );
  }

  const shown = detail || snapshots?.snapshots?.[0];
  const tone = STATE_TONE[shown?.evidence_state || status?.state || ''] || 'text-slate-300';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Scale className="w-6 h-6 text-teal-400" />
            <span>Real-World Evidence</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Measured champion/challenger evidence only · no winner, no ranking, no promotion.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors self-start sm:self-auto"
          title="Refresh evidence"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Evidence Status</h2>
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-mono">
          <span className={`font-semibold ${tone}`}>{status?.state}</span>
          <span className="text-slate-400">paired: {status?.paired_observations ?? 0}</span>
          <span className="text-slate-400">champion evals: {status?.champion_evaluations ?? 0}</span>
          <span className="text-slate-400">challenger evals: {status?.challenger_evaluations ?? 0}</span>
          <span className="text-slate-400">synthetic: {status?.synthetic_observations ?? 0}</span>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Evidence Snapshots</h2>
        {(snapshots?.snapshots || []).length === 0 ? (
          <div className="text-xs font-mono text-slate-500 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            No evidence snapshots yet — expected while real observations accumulate.
          </div>
        ) : (
          <div className="space-y-2">
            {(snapshots?.snapshots || []).map((s) => (
              <button
                key={s.snapshot_id}
                onClick={() => setSnapshotId(s.snapshot_id)}
                className={`w-full text-left p-3 rounded-xl border transition-colors ${
                  shown?.snapshot_id === s.snapshot_id
                    ? 'border-teal-500/50 bg-teal-500/5'
                    : 'border-surface-border bg-surface-card hover:border-slate-600'
                }`}
              >
                <div className="flex items-center justify-between gap-2 text-xs font-mono">
                  <span className="text-slate-200">{s.snapshot_id}</span>
                  <span className={STATE_TONE[s.evidence_state] || 'text-slate-300'}>
                    {s.evidence_state}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-500 mt-1">
                  paired {s.paired_count} · excluded {s.excluded_count} · {s.created_at}
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {shown && (
        <section className="space-y-3">
          <h2 className="text-base font-semibold text-slate-100">Paired Differences</h2>
          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
            <div className="grid grid-cols-4 gap-3 text-center text-xs font-mono">
              <div className="text-slate-500">metric</div>
              <div className="text-slate-500">champion</div>
              <div className="text-slate-500">challenger</div>
              <div className="text-slate-500">difference</div>
              {['accuracy_1x2', 'log_loss_1x2', 'brier_1x2', 'goal_mae'].map((k) => (
                <React.Fragment key={k}>
                  <div className="text-slate-400">{k}</div>
                  <div className="text-slate-200">{fmt(shown.champion_metrics?.[k])}</div>
                  <div className="text-slate-200">{fmt(shown.challenger_metrics?.[k])}</div>
                  <div className="text-slate-200">{fmt(shown.differences?.[`delta_${k}`])}</div>
                </React.Fragment>
              ))}
            </div>
            <div className="text-[11px] font-mono text-slate-500">
              uncertainty: seeded bootstrap CIs · sample sizes exposed · small samples flagged
            </div>
          </div>
        </section>
      )}
    </div>
  );
};
