import React from 'react';
import { GitCompare, HelpCircle } from 'lucide-react';
import { ModelDisagreementSection } from '../../api/types';
import { formatProbability } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface ModelAgreementTableProps {
  disagreement: ModelDisagreementSection;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const ModelAgreementTable: React.FC<ModelAgreementTableProps> = ({
  disagreement,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const members = disagreement.members || {};
  const perOutcome = disagreement.per_outcome || {};

  const modelKeys = ['elo', 'poisson', 'advanced', 'ensemble'];
  const outcomes = [
    { key: 'home', label: `Home (${homeTeamName})` },
    { key: 'draw', label: 'Draw' },
    { key: 'away', label: `Away (${awayTeamName})` },
  ];

  return (
    <section aria-labelledby="model-agreement-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">
            <GitCompare className="w-4 h-4" />
          </div>
          <div>
            <h2 id="model-agreement-heading" className="font-semibold text-sm text-slate-100">
              Model Agreement & Variance Matrix
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Cross-model comparison across individual components (unranked)
            </span>
          </div>
        </div>

        <Badge variant="outline" size="sm">
          {disagreement.label || 'Descriptive comparison only'}
        </Badge>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono border-collapse" aria-label="Model Agreement Table">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
              <th className="p-2.5 text-left font-medium">Outcome</th>
              <th className="p-2.5 text-center font-medium">Elo</th>
              <th className="p-2.5 text-center font-medium">Poisson</th>
              <th className="p-2.5 text-center font-medium">Advanced</th>
              <th className="p-2.5 text-center font-medium">Ensemble</th>
              <th className="p-2.5 text-center font-medium border-l border-slate-800 text-slate-400">Mean</th>
              <th className="p-2.5 text-center font-medium text-slate-400">Std Dev</th>
              <th className="p-2.5 text-center font-medium text-slate-400">Range</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {outcomes.map((item) => {
              const stats = perOutcome[item.key] || {};

              return (
                <tr key={item.key} className="hover:bg-slate-900/40 transition-colors">
                  <td className="p-2.5 font-semibold text-slate-200">{item.label}</td>

                  {/* Individual Models */}
                  {modelKeys.map((k) => {
                    const member = members[k];
                    const isValid = member?.status === 'valid';
                    const prob = (member as any)?.[item.key];

                    return (
                      <td key={k} className="p-2.5 text-center">
                        {isValid && prob !== undefined && prob !== null ? (
                          <span className="text-slate-100 font-medium">
                            {formatProbability(prob)}
                          </span>
                        ) : (
                          <span
                            className="text-slate-400 text-[11px] italic"
                            title={member?.notes?.join(', ') || 'Insufficient sample or not fitted'}
                          >
                            {member?.status || 'N/A'}
                          </span>
                        )}
                      </td>
                    );
                  })}

                  {/* Summary Statistics */}
                  <td className="p-2.5 text-center border-l border-slate-800 font-semibold text-slate-200">
                    {stats.mean !== undefined ? formatProbability(stats.mean) : '—'}
                  </td>
                  <td className="p-2.5 text-center text-slate-400">
                    {stats.std !== undefined ? stats.std.toFixed(3) : '—'}
                  </td>
                  <td className="p-2.5 text-center text-slate-400">
                    {stats.range !== undefined ? formatProbability(stats.range) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="pt-2 text-[11px] text-slate-400 font-sans leading-relaxed">
        <strong>Methodological Note:</strong> Models are not ranked in superiority. Different architectures capture distinct football dynamics: Elo assesses long-term relative quality, Poisson evaluates venue-split scoring rates, and Ensemble synthesizes them.
      </div>
    </section>
  );
};
