import React from 'react';
import { CheckCircle2, XCircle, MinusCircle, Target } from 'lucide-react';
import { MatchEvaluationResponse } from '../../api/types';

export interface EvaluationSectionProps {
  evaluation: MatchEvaluationResponse | undefined;
  isLoading?: boolean;
  predictedHome?: number | null;
  predictedDraw?: number | null;
  predictedAway?: number | null;
}

const fmt = (v: any, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

export const EvaluationSection: React.FC<EvaluationSectionProps> = ({
  evaluation,
  isLoading,
  predictedHome,
  predictedDraw,
  predictedAway,
}) => {
  if (isLoading) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
        <span className="text-xs font-mono text-slate-400">Loading post-match evaluation…</span>
      </section>
    );
  }

  if (!evaluation || !evaluation.outcome) {
    return null;
  }

  const latest = evaluation.evaluations[evaluation.evaluations.length - 1];
  const m = latest?.metrics || {};
  const hit = m.accuracy_1x2 === 1;

  return (
    <section
      aria-labelledby="evaluation-heading"
      className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-teal-500/10 border border-teal-500/20 text-teal-400">
            <Target className="w-4 h-4" />
          </div>
          <div>
            <h2 id="evaluation-heading" className="font-semibold text-sm text-slate-100">
              Post-Match Evaluation
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Phase 27 immutable scoring · prediction snapshot untouched
            </span>
          </div>
        </div>
        <div className={`flex items-center gap-1.5 ${hit ? 'text-emerald-400' : 'text-red-400'}`}>
          {hit ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          <span className="text-xs font-mono font-semibold">
            1X2 {hit ? 'Hit' : 'Miss'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <div>
          <div className="text-slate-500">Predicted 1X2</div>
          <div className="text-slate-200">
            {fmt(predictedHome)} / {fmt(predictedDraw)} / {fmt(predictedAway)}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Final score</div>
          <div className="text-slate-200">
            {evaluation.final_score.home} – {evaluation.final_score.away} ({m.actual_result || '—'})
          </div>
        </div>
        <div>
          <div className="text-slate-500">Log loss</div>
          <div className="text-slate-200">{fmt(m.log_loss_1x2)}</div>
        </div>
        <div>
          <div className="text-slate-500">Brier</div>
          <div className="text-slate-200">{fmt(m.brier_1x2)}</div>
        </div>
        <div>
          <div className="text-slate-500">Goal MAE</div>
          <div className="text-slate-200">{fmt(m.goal_mae)}</div>
        </div>
        <div>
          <div className="text-slate-500">O/U 2.5</div>
          <div className="text-slate-200">
            {m.ou_2_5_accuracy === 1 ? 'Hit' : m.ou_2_5_accuracy === 0 ? 'Miss' : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">BTTS</div>
          <div className="text-slate-200">
            {m.btts_accuracy === 1 ? 'Hit' : m.btts_accuracy === 0 ? 'Miss' : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Exact score</div>
          <div className="text-slate-200 flex items-center gap-1">
            {m.exact_score_hit === 1 ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            ) : m.exact_score_hit === 0 ? (
              <MinusCircle className="w-3.5 h-3.5 text-slate-500" />
            ) : null}
            {m.predicted_top_score || '—'}
          </div>
        </div>
      </div>
    </section>
  );
};
