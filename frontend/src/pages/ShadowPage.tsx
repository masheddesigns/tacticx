import React, { useState } from 'react';
import { GitCompareArrows, RefreshCw, FlaskConical } from 'lucide-react';
import {
  useShadowSummary,
  useShadowChallengers,
  useShadowComparison,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

const fmt = (v: any, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

export const ShadowPage: React.FC = () => {
  const [challenger, setChallenger] = useState<string>('');

  const { data: summary, isLoading, error, refetch } = useShadowSummary();
  const { data: challengers } = useShadowChallengers();
  const activeId = challenger || (challengers?.challengers?.[0] || '');
  const { data: comparison } = useShadowComparison(activeId);

  if (isLoading) {
    return <LoadingSpinner label="Loading shadow pipeline…" />;
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <ErrorCard error={error as Error} title="Shadow Unavailable" onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <GitCompareArrows className="w-6 h-6 text-violet-400" />
            <span>Champion / Challenger Shadow</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Same cutoff, shared feature snapshot, isolated outputs · factual comparison only, no winner.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={challenger}
            onChange={(e) => setChallenger(e.target.value)}
            className="px-2 py-1.5 rounded-lg border border-slate-700 bg-slate-900 text-xs font-mono text-slate-200"
          >
            <option value="">Select challenger…</option>
            {(challengers?.challengers || []).map((c: string) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors"
            title="Refresh shadow"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Shadow Status</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 rounded-xl border border-surface-border bg-surface-card">
            <div className="text-slate-500">Executed</div>
            <div className="text-slate-100 text-sm font-semibold">{summary?.shadow_executions ?? 0}</div>
          </div>
          <div className="p-3 rounded-xl border border-surface-border bg-surface-card">
            <div className="text-slate-500">Evaluated</div>
            <div className="text-slate-100 text-sm font-semibold">{summary?.shadow_evaluations ?? 0}</div>
          </div>
          <div className="p-3 rounded-xl border border-surface-border bg-surface-card">
            <div className="text-slate-500">Eval coverage</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(summary?.evaluation_coverage_rate)}</div>
          </div>
          <div className="p-3 rounded-xl border border-surface-border bg-surface-card">
            <div className="text-slate-500">Challengers</div>
            <div className="text-slate-100 text-sm font-semibold">
              {Object.keys(summary?.by_challenger || {}).length}
            </div>
          </div>
        </div>
      </section>

      {activeId ? (
        <ComparisonSection challengerId={activeId} comparison={comparison} />
      ) : (
        <div className="text-xs font-mono text-slate-500 flex items-center gap-2">
          <FlaskConical className="w-4 h-4" />
          No challenger with shadow executions yet.
        </div>
      )}
    </div>
  );
};

const ComparisonSection: React.FC<{ challengerId: string; comparison?: any }> = ({
  challengerId,
  comparison,
}) => {
  if (!comparison) {
    return <div className="text-xs font-mono text-slate-500">Select a challenger to compare.</div>;
  }
  const agg = comparison.aggregate || {};
  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-slate-100">
        Champion vs Challenger <span className="text-slate-500 font-mono text-xs">{challengerId}</span>
      </h2>
      <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
        <div className="text-[11px] font-mono text-slate-500">
          evaluated pairs: {comparison.evaluated_pairs ?? 0} · evidence: {agg.evidence || '—'}
        </div>
        <div className="grid grid-cols-4 gap-3 text-center text-xs font-mono">
          <div className="text-slate-500">metric</div>
          <div className="text-slate-500">champion</div>
          <div className="text-slate-500">challenger</div>
          <div className="text-slate-500">difference</div>
          {['accuracy_1x2', 'log_loss_1x2', 'brier_1x2', 'goal_mae'].map((k) => (
            <React.Fragment key={k}>
              <div className="text-slate-400">{k}</div>
              <div className="text-slate-200">{fmt(agg[`champion_${k}`])}</div>
              <div className="text-slate-200">{fmt(agg[`challenger_${k}`])}</div>
              <div className="text-slate-200">{fmt(agg[`delta_${k}`])}</div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </section>
  );
};
