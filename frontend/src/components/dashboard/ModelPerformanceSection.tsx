import React from 'react';
import { Activity, AlertCircle } from 'lucide-react';
import {
  EvaluationsSummaryResponse,
  CalibrationResponse,
  DriftResponse,
} from '../../api/types';

export interface ModelPerformanceSectionProps {
  summary?: EvaluationsSummaryResponse;
  calibration?: CalibrationResponse;
  drift?: DriftResponse;
  isLoading?: boolean;
}

const fmt = (v: any, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

export const ModelPerformanceSection: React.FC<ModelPerformanceSectionProps> = ({
  summary,
  calibration,
  drift,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <section className="space-y-4">
        <span className="text-xs font-mono text-slate-400">Loading production performance…</span>
      </section>
    );
  }

  const metrics = summary?.metrics || {};
  const n = metrics.sample_count ?? 0;

  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
        <Activity className="w-4 h-4 text-teal-400" />
        Production Prediction Performance
        <span className="text-[11px] font-mono text-slate-500">
          Phase 27 measurement only · no auto-promotion
        </span>
      </h2>

      <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div>
            <div className="text-slate-500">Evaluated</div>
            <div className="text-slate-100 text-sm font-semibold">{n}</div>
          </div>
          <div>
            <div className="text-slate-500">Accuracy 1X2</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.accuracy_1x2)}</div>
          </div>
          <div>
            <div className="text-slate-500">Log loss</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.log_loss_1x2)}</div>
          </div>
          <div>
            <div className="text-slate-500">Brier</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.brier_1x2)}</div>
          </div>
          <div>
            <div className="text-slate-500">Goal MAE</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.goal_mae)}</div>
          </div>
          <div>
            <div className="text-slate-500">Goal RMSE</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.goal_rmse)}</div>
          </div>
          <div>
            <div className="text-slate-500">O/U 2.5 acc</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.ou_2_5_accuracy)}</div>
          </div>
          <div>
            <div className="text-slate-500">Exact-score hit</div>
            <div className="text-slate-100 text-sm font-semibold">{fmt(metrics.exact_score_hit)}</div>
          </div>
        </div>
        {summary?.evaluation_period?.from && (
          <div className="text-[11px] font-mono text-slate-500">
            Period: {summary.evaluation_period.from} → {summary.evaluation_period.to}
          </div>
        )}
      </div>

      <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
        <div className="text-xs font-mono font-semibold text-slate-300">
          Calibration (1X2 reliability, 10 bins)
        </div>
        {(['home', 'draw', 'away'] as const).map((o) => {
          const entry = calibration?.per_outcome?.[o];
          return (
            <div key={o} className="text-xs font-mono text-slate-400">
              <span className="text-slate-200 capitalize">{o}</span>
              {' · n='}{entry?.sample_count ?? 0}
              {' · ECE='}{fmt(entry?.ece)}
            </div>
          );
        })}
      </div>

      <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
        <div className="text-xs font-mono font-semibold text-slate-300 flex items-center gap-2">
          Drift (recent {drift?.recent_n_requested ?? 50} vs baseline)
          {!drift?.sufficient_sample && (
            <span className="inline-flex items-center gap-1 text-amber-400 text-[11px]">
              <AlertCircle className="w-3.5 h-3.5" />
              insufficient sample (min {drift?.min_sample ?? 20})
            </span>
          )}
        </div>
        <div className="text-xs font-mono text-slate-400">
          recent n={drift?.recent_sample ?? 0} · baseline n={drift?.baseline_sample ?? 0}
          {' · Δacc='}{fmt(drift?.differences_recent_minus_baseline?.accuracy_1x2)}
          {' · Δbrier='}{fmt(drift?.differences_recent_minus_baseline?.brier_1x2)}
        </div>
      </div>
    </section>
  );
};
