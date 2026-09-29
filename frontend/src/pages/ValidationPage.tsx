import React, { useState } from 'react';
import { ShieldCheck, RefreshCw } from 'lucide-react';
import {
  useValidationStatus,
  useValidationConfig,
  useValidationCandidates,
  useValidationDetail,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

const RULE_TONE: Record<string, string> = {
  PASS: 'text-emerald-400',
  BLOCKED: 'text-red-400',
  INSUFFICIENT_DATA: 'text-amber-400',
  INCONCLUSIVE: 'text-slate-300',
  WARNING: 'text-orange-400',
};

export const ValidationPage: React.FC = () => {
  const [validationId, setValidationId] = useState<string>('');

  const { data: status, isLoading, error, refetch } = useValidationStatus();
  const { data: config } = useValidationConfig();
  const { data: candidates } = useValidationCandidates();
  const { data: detail } = useValidationDetail(validationId);

  if (isLoading) {
    return <LoadingSpinner label="Loading candidate validation…" />;
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <ErrorCard error={error as Error} title="Validation Unavailable" onRetry={() => refetch()} />
      </div>
    );
  }

  const rules: any[] = detail?.rule_results?.rules || [];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-emerald-400" />
            <span>Candidate Validation</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Evidence readiness for human governance review · never an approval or promotion.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={validationId}
            onChange={(e) => setValidationId(e.target.value)}
            placeholder="validation_id"
            className="px-2 py-1.5 rounded-lg border border-slate-700 bg-slate-900 text-xs font-mono text-slate-200 w-52"
          />
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors"
            title="Refresh validation"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Current Champion</h2>
        <div className="p-4 rounded-xl border border-emerald-500/20 bg-surface-card text-xs font-mono text-slate-200">
          ensemble_v1-elo+poisson · validations: {status?.validation_count ?? 0} · config:{' '}
          {config?.config_id}@v{config?.config_version}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Validated Candidates</h2>
        {(candidates?.candidates || []).length === 0 ? (
          <div className="text-xs font-mono text-slate-500">
            No candidates validated yet — expected while real evidence accumulates.
          </div>
        ) : (
          <div className="text-xs font-mono text-slate-300 space-y-1">
            {(candidates?.candidates || []).map((c: string) => (
              <div key={c}>{c}</div>
            ))}
          </div>
        )}
      </section>

      {detail && (
        <section className="space-y-3">
          <h2 className="text-base font-semibold text-slate-100">
            Validation <span className="font-mono text-xs text-slate-400">{detail.validation_id}</span>
          </h2>
          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-3">
            <div className="text-xs font-mono text-slate-300">
              state: <span className="font-semibold">{detail.validation_state}</span> · evidence:{' '}
              {detail.evidence_state || '—'}
            </div>
            <ul className="space-y-1.5">
              {rules.map((r) => (
                <li key={r.rule_id} className="text-[11px] font-mono flex items-start gap-2">
                  <span className={RULE_TONE[r.state] || 'text-slate-400'}>[{r.state}]</span>
                  <span className="text-slate-300">{r.rule_id}</span>
                  <span className="text-slate-500">— {r.explanation}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
};
