import React from 'react';
import { Target, Info } from 'lucide-react';
import { ExpectedGoalsSection } from '../../api/types';
import { formatLambda } from '../../lib/utils';

export interface ExpectedGoalsCardProps {
  goals: ExpectedGoalsSection;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const ExpectedGoalsCard: React.FC<ExpectedGoalsCardProps> = ({
  goals,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const homeLambda = goals.home_lambda ?? 0;
  const awayLambda = goals.away_lambda ?? 0;
  const totalLambda = goals.total_lambda ?? homeLambda + awayLambda;

  // Max scale for visualization (e.g. 3.5 goals)
  const maxScale = Math.max(3.5, homeLambda, awayLambda, 1);
  const homePct = Math.min(100, (homeLambda / maxScale) * 100);
  const awayPct = Math.min(100, (awayLambda / maxScale) * 100);

  return (
    <section aria-labelledby="expected-goals-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">
            <Target className="w-4 h-4" />
          </div>
          <div>
            <h2 id="expected-goals-heading" className="font-semibold text-sm text-slate-100">
              Expected Goals (λ) Estimates
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Poisson scoring rate intensities (model estimates, not predicted scores)
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Home Expected Goals */}
        <div className="p-4 rounded-lg bg-slate-900/70 border border-slate-800 flex flex-col justify-between">
          <div>
            <span className="text-xs font-mono text-slate-400 block truncate" title={homeTeamName}>
              Home λ ({homeTeamName})
            </span>
            <div className="text-2xl font-mono font-bold text-blue-400 mt-1">
              {formatLambda(homeLambda)}
            </div>
            <span className="text-[10px] text-slate-400 font-sans mt-0.5 block">
              Estimated scoring intensity
            </span>
          </div>
          <div className="w-full bg-slate-950 h-2 rounded-full mt-3 overflow-hidden border border-slate-800">
            <div
              style={{ width: `${homePct}%` }}
              className="bg-blue-500 h-full rounded-full transition-all"
            />
          </div>
        </div>

        {/* Away Expected Goals */}
        <div className="p-4 rounded-lg bg-slate-900/70 border border-slate-800 flex flex-col justify-between">
          <div>
            <span className="text-xs font-mono text-slate-400 block truncate" title={awayTeamName}>
              Away λ ({awayTeamName})
            </span>
            <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
              {formatLambda(awayLambda)}
            </div>
            <span className="text-[10px] text-slate-400 font-sans mt-0.5 block">
              Estimated scoring intensity
            </span>
          </div>
          <div className="w-full bg-slate-950 h-2 rounded-full mt-3 overflow-hidden border border-slate-800">
            <div
              style={{ width: `${awayPct}%` }}
              className="bg-emerald-500 h-full rounded-full transition-all"
            />
          </div>
        </div>

        {/* Combined Expected Goals */}
        <div className="p-4 rounded-lg bg-slate-900/70 border border-slate-800 flex flex-col justify-between">
          <div>
            <span className="text-xs font-mono text-slate-400 block">Combined Total λ</span>
            <div className="text-2xl font-mono font-bold text-purple-400 mt-1">
              {formatLambda(totalLambda)}
            </div>
            <span className="text-[10px] text-slate-400 font-sans mt-0.5 block">
              Expected total match goals
            </span>
          </div>
          <div className="mt-3 text-[11px] font-mono text-slate-400 flex items-center justify-between">
            <span>Rate split:</span>
            <span>
              {homeLambda + awayLambda > 0
                ? `${Math.round((homeLambda / (homeLambda + awayLambda)) * 100)}% / ${Math.round((awayLambda / (homeLambda + awayLambda)) * 100)}%`
                : '—'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 p-2.5 rounded bg-slate-950 border border-slate-800/80 text-[11px] text-slate-400 font-sans">
        <Info className="w-3.5 h-3.5 text-slate-500 shrink-0" />
        <span>
          λ represents the Poisson distribution rate parameter. It is a continuous statistical intensity estimate, not a discrete prediction of the match result.
        </span>
      </div>
    </section>
  );
};
