import React from 'react';
import { formatProbability } from '../../lib/utils';
import { TeamLogo } from '../common/TeamLogo';

export interface ProbabilityBarProps {
  home: number | null | undefined;
  draw: number | null | undefined;
  away: number | null | undefined;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const ProbabilityBar: React.FC<ProbabilityBarProps> = ({
  home,
  draw,
  away,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const h = home ?? 0;
  const d = draw ?? 0;
  const a = away ?? 0;
  const total = h + d + a || 1;

  const hPct = (h / total) * 100;
  const dPct = (d / total) * 100;
  const aPct = (a / total) * 100;

  return (
    <div className="w-full space-y-2">
      {/* 1X2 Horizontal Bar */}
      <div
        role="progressbar"
        aria-label={`Model outcome probabilities: ${homeTeamName} ${formatProbability(h)}, Draw ${formatProbability(d)}, ${awayTeamName} ${formatProbability(a)}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(hPct)}
        className="h-7 w-full flex rounded-lg overflow-hidden border border-slate-800 bg-slate-950 p-0.5 gap-0.5"
      >
        {/* Home Probability Segment */}
        <div
          style={{ width: `${hPct}%` }}
          className="h-full bg-blue-600/70 hover:bg-blue-600 rounded-l flex items-center justify-center transition-all cursor-pointer group relative"
          title={`${homeTeamName} (Home): ${formatProbability(h, 2)} (Exact: ${h})`}
        >
          {hPct > 12 && (
            <span className="text-[11px] font-mono font-bold text-blue-100 truncate px-1">
              {formatProbability(h)}
            </span>
          )}
        </div>

        {/* Draw Probability Segment */}
        <div
          style={{ width: `${dPct}%` }}
          className="h-full bg-slate-600/70 hover:bg-slate-600 flex items-center justify-center transition-all cursor-pointer group relative"
          title={`Draw: ${formatProbability(d, 2)} (Exact: ${d})`}
        >
          {dPct > 12 && (
            <span className="text-[11px] font-mono font-bold text-slate-200 truncate px-1">
              {formatProbability(d)}
            </span>
          )}
        </div>

        {/* Away Probability Segment */}
        <div
          style={{ width: `${aPct}%` }}
          className="h-full bg-emerald-600/70 hover:bg-emerald-600 rounded-r flex items-center justify-center transition-all cursor-pointer group relative"
          title={`${awayTeamName} (Away): ${formatProbability(a, 2)} (Exact: ${a})`}
        >
          {aPct > 12 && (
            <span className="text-[11px] font-mono font-bold text-emerald-100 truncate px-1">
              {formatProbability(a)}
            </span>
          )}
        </div>
      </div>

      {/* Accessible Outcome Legend */}
      <div className="flex items-center justify-between text-xs font-mono pt-1 text-slate-300">
        <div className="flex items-center gap-1.5 min-w-0">
          <TeamLogo teamName={homeTeamName} size="xs" />
          <span className="text-slate-400 truncate">Home ({homeTeamName}):</span>
          <span className="font-semibold text-slate-100 shrink-0">{formatProbability(h)}</span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 px-2">
          <span className="w-2 h-2 rounded-full bg-slate-400 inline-block" aria-hidden="true" />
          <span className="text-slate-400">Draw:</span>
          <span className="font-semibold text-slate-100">{formatProbability(d)}</span>
        </div>

        <div className="flex items-center gap-1.5 min-w-0 justify-end">
          <TeamLogo teamName={awayTeamName} size="xs" />
          <span className="text-slate-400 truncate">Away ({awayTeamName}):</span>
          <span className="font-semibold text-slate-100 shrink-0">{formatProbability(a)}</span>
        </div>
      </div>
    </div>
  );
};
