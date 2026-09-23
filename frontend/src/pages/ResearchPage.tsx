import React, { useState } from 'react';
import { FlaskConical, RefreshCw, ShieldAlert, CheckCircle2 } from 'lucide-react';
import {
  useResearchCandidates,
  useResearchDatasets,
  useResearchExperiments,
  useResearchExperiment,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

const fmt = (v: any, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

export const ResearchPage: React.FC = () => {
  const [selectedExperiment, setSelectedExperiment] = useState<string>('');

  const { data: candidates, isLoading: candLoading, error: candError } = useResearchCandidates();
  const { data: datasets } = useResearchDatasets();
  const { data: experiments, refetch: refetchExps } = useResearchExperiments();
  const { data: detail } = useResearchExperiment(selectedExperiment);

  if (candLoading) {
    return <LoadingSpinner label="Loading research registry…" />;
  }

  if (candError) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <ErrorCard error={candError as Error} title="Research Unavailable" onRetry={() => refetchExps()} />
      </div>
    );
  }

  const shown = detail || (experiments?.experiments?.[0] as any);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <FlaskConical className="w-6 h-6 text-violet-400" />
            <span>Research Experiments</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Controlled candidate evidence only · production ensemble_v1 is locked · no auto-promotion.
          </p>
        </div>
        <button
          onClick={() => refetchExps()}
          className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors self-start sm:self-auto"
          title="Refresh registry"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Candidates</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(candidates?.candidates || []).map((c) => (
            <div key={c.candidate_id} className="p-4 rounded-xl border border-surface-border bg-surface-card">
              <div className="text-sm font-semibold text-slate-100">{c.name}</div>
              <div className="text-[11px] font-mono text-slate-500 mt-1">
                {c.candidate_id} · {c.model_family} · {c.status}
              </div>
              <div className="text-xs text-slate-400 mt-2">{c.hypothesis}</div>
            </div>
          ))}
          {(candidates?.candidates || []).length === 0 && (
            <div className="text-xs font-mono text-slate-500">No candidates registered.</div>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Datasets</h2>
        <div className="text-xs font-mono text-slate-300 space-y-1">
          {(datasets?.datasets || []).map((d) => (
            <div key={d.dataset_id}>
              {d.dataset_id} · n={d.observation_count} · {d.cutoff_policy} · hash {d.dataset_hash?.slice(0, 12)}
            </div>
          ))}
          {(datasets?.datasets || []).length === 0 && (
            <div className="text-slate-500">No datasets built.</div>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Experiments</h2>
        <div className="space-y-3">
          {(experiments?.experiments || []).map((e) => (
            <button
              key={e.experiment_id}
              onClick={() => setSelectedExperiment(e.experiment_id)}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                shown?.experiment_id === e.experiment_id
                  ? 'border-violet-500/50 bg-violet-500/5'
                  : 'border-surface-border bg-surface-card hover:border-slate-600'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-mono text-slate-200">{e.experiment_id}</span>
                <span className="text-[11px] font-mono text-slate-400">{e.evidence_state}</span>
              </div>
              <div className="text-[11px] font-mono text-slate-500 mt-1">
                leakage {e.leakage_status} · seed {e.reproducibility?.random_seed} · hash{' '}
                {e.result_hash?.slice(0, 12)}
              </div>
            </button>
          ))}
          {(experiments?.experiments || []).length === 0 && (
            <div className="text-xs font-mono text-slate-500">No experiments run.</div>
          )}
        </div>
      </section>

      {shown && (
        <section className="space-y-3">
          <h2 className="text-base font-semibold text-slate-100">Comparison</h2>
          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
            <div className="flex items-center gap-2 text-xs font-mono">
              {shown.leakage_status === 'PASS' ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-red-400" />
              )}
              <span className="text-slate-200">{shown.evidence_state}</span>
              <span className="text-slate-500">leakage: {shown.leakage_status}</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center text-xs font-mono">
              <div className="text-slate-500">metric</div>
              <div className="text-slate-500">baseline</div>
              <div className="text-slate-500">candidate</div>
              {['accuracy_1x2', 'log_loss_1x2', 'brier_1x2'].map((k) => (
                <React.Fragment key={k}>
                  <div className="text-slate-400">{k}</div>
                  <div className="text-slate-200">{fmt(shown.baseline_metrics?.[k])}</div>
                  <div className="text-slate-200">{fmt(shown.candidate_metrics?.[k])}</div>
                </React.Fragment>
              ))}
            </div>
            <div className="text-[11px] font-mono text-slate-500">
              Δlogloss {fmt(shown.comparison?.delta_log_loss, 6)} · Δbrier{' '}
              {fmt(shown.comparison?.delta_brier, 6)} · n={shown.comparison?.n} · dataset{' '}
              {shown.dataset_hash?.slice(0, 12)} · code {shown.reproducibility?.runner_code_hash?.slice(0, 12)}
            </div>
          </div>
        </section>
      )}
    </div>
  );
};
