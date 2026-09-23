import React from 'react';
import { CheckCircle2, XCircle, AlertCircle, MinusCircle, Zap } from 'lucide-react';
import { PredictionSnapshotsResponse } from '../../api/types';
import { Badge } from '../common/Badge';

export interface PredictionExecutionSectionProps {
  execution: PredictionSnapshotsResponse | undefined;
  isLoading?: boolean;
}

const STATUS_META: Record<string, { label: string; icon: React.ReactNode; tone: string }> = {
  GENERATED: {
    label: 'Generated',
    icon: <CheckCircle2 className="w-4 h-4" />,
    tone: 'text-emerald-400',
  },
  DEGRADED: {
    label: 'Generated (Degraded)',
    icon: <AlertCircle className="w-4 h-4" />,
    tone: 'text-amber-400',
  },
  BLOCKED: {
    label: 'Blocked',
    icon: <XCircle className="w-4 h-4" />,
    tone: 'text-red-400',
  },
  NOT_GENERATED: {
    label: 'Not Generated',
    icon: <MinusCircle className="w-4 h-4" />,
    tone: 'text-slate-400',
  },
};

export const PredictionExecutionSection: React.FC<PredictionExecutionSectionProps> = ({
  execution,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
        <span className="text-xs font-mono text-slate-400">Loading prediction execution…</span>
      </section>
    );
  }

  if (!execution) {
    return null;
  }

  const meta = STATUS_META[execution.status] || STATUS_META.NOT_GENERATED;
  const latest = execution.latest;
  const payload = latest?.prediction_payload?.prediction;

  return (
    <section
      aria-labelledby="prediction-execution-heading"
      className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-violet-500/10 border border-violet-500/20 text-violet-400">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <h2 id="prediction-execution-heading" className="font-semibold text-sm text-slate-100">
              Pre-Match Prediction Execution
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Phase 26 immutable snapshot · readiness-bound · cutoff-safe
            </span>
          </div>
        </div>
        <div className={`flex items-center gap-1.5 ${meta.tone}`}>
          {meta.icon}
          <span className="text-xs font-mono font-semibold">{meta.label}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <div>
          <div className="text-slate-500">Model</div>
          <div className="text-slate-200">{latest?.model_version || '—'}</div>
        </div>
        <div>
          <div className="text-slate-500">Mode</div>
          <div className="text-slate-200">{latest?.prediction_mode || 'PRE_MATCH'}</div>
        </div>
        <div>
          <div className="text-slate-500">Cutoff</div>
          <div className="text-slate-200">{latest?.cutoff_time || '—'}</div>
        </div>
        <div>
          <div className="text-slate-500">Readiness</div>
          <div className="text-slate-200">
            {latest?.readiness_state || execution.latest_readiness_state || '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Version</div>
          <div className="text-slate-200">
            {latest ? `v${latest.prediction_version}` : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Generated</div>
          <div className="text-slate-200">{latest?.created_at || '—'}</div>
        </div>
        <div className="col-span-2">
          <div className="text-slate-500">Prediction hash</div>
          <div className="text-slate-200 truncate">
            {latest?.prediction_hash || '—'}
          </div>
        </div>
      </div>

      {payload && (
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { label: 'Home', value: payload.home_win_probability },
            { label: 'Draw', value: payload.draw_probability },
            { label: 'Away', value: payload.away_win_probability },
          ].map((row) => (
            <div key={row.label} className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
              <div className="text-[11px] font-mono text-slate-500">{row.label}</div>
              <div className="text-sm font-mono font-semibold text-slate-100">
                {typeof row.value === 'number' ? row.value.toFixed(4) : '—'}
              </div>
            </div>
          ))}
        </div>
      )}

      {execution.prediction_count > 1 && (
        <div className="flex items-center gap-2">
          <Badge variant="outline" size="sm">
            {execution.prediction_count} snapshots
          </Badge>
          <span className="text-[11px] font-mono text-slate-500">
            showing latest · history is immutable
          </span>
        </div>
      )}
    </section>
  );
};
