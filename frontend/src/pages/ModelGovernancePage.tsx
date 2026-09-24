import React from 'react';
import { ShieldCheck, RefreshCw, History, GitBranch } from 'lucide-react';
import {
  useChampion,
  useGovernanceRegistry,
  usePromotionRequests,
  useGovernanceAudit,
} from '../api/queries';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

export const ModelGovernancePage: React.FC = () => {
  const { data: champion, isLoading, error, refetch } = useChampion();
  const { data: registry } = useGovernanceRegistry();
  const { data: requests } = usePromotionRequests();
  const { data: audit } = useGovernanceAudit();

  if (isLoading) {
    return <LoadingSpinner label="Loading model governance…" />;
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <ErrorCard error={error as Error} title="Governance Unavailable" onRetry={() => refetch()} />
      </div>
    );
  }

  const challengers = (registry?.bindings || []).filter((b: any) => b.role === 'CHALLENGER');

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-emerald-400" />
            <span>Model Governance</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Human-gated promotion authority · research evidence never auto-promotes · no model rankings.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors self-start sm:self-auto"
          title="Refresh governance"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Current Production Champion</h2>
        <div className="p-4 rounded-xl border border-emerald-500/20 bg-surface-card space-y-1">
          <div className="text-sm font-mono font-semibold text-slate-100">
            {champion?.artifact?.model_id} · {champion?.artifact?.model_version}
          </div>
          <div className="text-[11px] font-mono text-slate-500">
            artifact {champion?.artifact?.artifact_id} · state {champion?.artifact?.lifecycle_state} ·
            bound {champion?.bound_at}
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-violet-400" />
          Challengers ({challengers.length})
        </h2>
        {challengers.length === 0 ? (
          <div className="text-xs font-mono text-slate-500">No challengers registered.</div>
        ) : (
          <div className="space-y-2">
            {challengers.map((b: any) => (
              <div key={b.registry_id} className="p-3 rounded-xl border border-surface-border bg-surface-card text-xs font-mono text-slate-300">
                {b.artifact_id} · {b.state} · {b.created_at}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100">Promotion Requests</h2>
        {(requests?.requests || []).length === 0 ? (
          <div className="text-xs font-mono text-slate-500">No promotion requests.</div>
        ) : (
          <div className="space-y-2">
            {(requests?.requests || []).map((r) => (
              <div key={r.request_id} className="p-3 rounded-xl border border-surface-border bg-surface-card text-xs font-mono text-slate-300">
                {r.request_id} · {r.deployment_mode} · {r.state} · by {r.requester || '—'}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
          <History className="w-4 h-4 text-slate-400" />
          Audit Trail
        </h2>
        <div className="p-4 rounded-xl border border-surface-border bg-surface-card max-h-96 overflow-y-auto">
          {(audit?.events || []).length === 0 ? (
            <div className="text-xs font-mono text-slate-500">No governance events.</div>
          ) : (
            <ul className="space-y-1.5">
              {(audit?.events || []).map((e) => (
                <li key={e.event_id} className="text-[11px] font-mono text-slate-400">
                  {e.created_at} · {e.artifact_id || '—'} · {e.from_state || '∅'} → {e.to_state} · {e.actor}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
};
