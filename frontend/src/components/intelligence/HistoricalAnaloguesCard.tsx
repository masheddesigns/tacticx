import React from 'react';
import { History, BookOpen, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { AnaloguesSection } from '../../api/types';
import { formatDateTime, formatProbability } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface HistoricalAnaloguesCardProps {
  analogues: AnaloguesSection;
}

export const HistoricalAnaloguesCard: React.FC<HistoricalAnaloguesCardProps> = ({ analogues }) => {
  const matches = analogues.analogues || [];
  const distribution = analogues.outcome_distribution;

  return (
    <section aria-labelledby="analogues-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-purple-500/10 border border-purple-500/20 text-purple-400">
            <History className="w-4 h-4" />
          </div>
          <div>
            <h2 id="analogues-heading" className="font-semibold text-sm text-slate-100">
              Historical Analogue Matches
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Pre-cutoff finished fixtures with similar statistical profile
            </span>
          </div>
        </div>

        {distribution && (
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-slate-400">Past Distribution (N={distribution.n}):</span>
            <span className="text-blue-400">H: {formatProbability(distribution.home)}</span>
            <span className="text-slate-300">D: {formatProbability(distribution.draw)}</span>
            <span className="text-emerald-400">A: {formatProbability(distribution.away)}</span>
          </div>
        )}
      </div>

      {matches.length === 0 ? (
        <div className="p-6 text-center text-xs font-mono text-slate-400">
          No historical analogues found for this fixture configuration.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono border-collapse" aria-label="Historical Analogues Table">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
                <th className="p-2.5 text-left font-medium">Match ID</th>
                <th className="p-2.5 text-left font-medium">Kickoff</th>
                <th className="p-2.5 text-center font-medium">Past Score</th>
                <th className="p-2.5 text-center font-medium">Outcome</th>
                <th className="p-2.5 text-right font-medium">Similarity</th>
                <th className="p-2.5 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {matches.slice(0, 8).map((m) => {
                const kickoff = formatDateTime(m.kickoff_at);
                return (
                  <tr key={m.match_id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="p-2.5 text-slate-300 font-semibold">Match #{m.match_id}</td>
                    <td className="p-2.5 text-slate-400">{kickoff.date}</td>
                    <td className="p-2.5 text-center font-bold text-slate-100">
                      {m.home_score} - {m.away_score}
                    </td>
                    <td className="p-2.5 text-center">
                      <Badge
                        variant={
                          m.actual === 'home'
                            ? 'info'
                            : m.actual === 'away'
                            ? 'success'
                            : 'default'
                        }
                        size="sm"
                      >
                        {m.actual.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="p-2.5 text-right font-bold text-emerald-400">
                      {(m.similarity * 100).toFixed(1)}%
                    </td>
                    <td className="p-2.5 text-right">
                      <Link
                        to={`/matches/${m.match_id}`}
                        className="inline-flex items-center gap-1 text-slate-400 hover:text-emerald-400 transition-colors"
                      >
                        <span>View</span>
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Methodology disclosure */}
      <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-400 font-sans space-y-1">
        <div className="flex items-center gap-1.5 font-semibold text-slate-300 font-mono text-xs">
          <BookOpen className="w-3.5 h-3.5 text-purple-400" />
          <span>Similarity Methodology Disclosure:</span>
        </div>
        <p className="leading-relaxed">
          {analogues.methodology ||
            'Historical matches selected using standardized Euclidean distance over pre-match feature vectors (Elo differences, form PPM, goal differential, and rest days). These are descriptive analogues from past completed fixtures; they do not establish causality or predict future results.'}
        </p>
      </div>
    </section>
  );
};
