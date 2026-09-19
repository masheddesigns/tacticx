import React, { useMemo } from 'react';
import { Grid, Sparkles, AlertCircle } from 'lucide-react';
import { CorrectScoreSection } from '../../api/types';
import { formatProbability } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface CorrectScoreGridProps {
  correctScore: CorrectScoreSection;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const CorrectScoreGrid: React.FC<CorrectScoreGridProps> = ({
  correctScore,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const distribution = correctScore.distribution || {};
  const topScores = correctScore.top_n || [];
  const topScore = topScores[0];

  // Build a 4x4 matrix: home 0..3, away 0..3
  const matrix = useMemo(() => {
    const rows = [0, 1, 2, 3];
    const cols = [0, 1, 2, 3];
    return rows.map((h) =>
      cols.map((a) => {
        const key = `${h}-${a}`;
        const prob = distribution[key] ?? 0;
        return { score: key, home: h, away: a, probability: prob };
      })
    );
  }, [distribution]);

  // Determine maximum probability in matrix for heatmap scaling
  const maxProb = useMemo(() => {
    let m = 0.001;
    matrix.forEach((row) => {
      row.forEach((cell) => {
        if (cell.probability > m) m = cell.probability;
      });
    });
    return m;
  }, [matrix]);

  return (
    <section aria-labelledby="correct-score-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Grid className="w-4 h-4" />
          </div>
          <div>
            <h2 id="correct-score-heading" className="font-semibold text-sm text-slate-100">
              Scoreline Probability Distribution
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Bivariate Poisson discrete scoreline matrix & tail mass
            </span>
          </div>
        </div>

        {topScore && (
          <div className="flex items-center gap-2 px-3 py-1 rounded bg-slate-900 border border-slate-800">
            <span className="text-[11px] font-mono text-slate-400">
              Highest-probability scoreline:
            </span>
            <span className="text-xs font-mono font-bold text-emerald-400">
              {topScore.score} ({formatProbability(topScore.probability)})
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Heatmap Grid (4x4) */}
        <div className="lg:col-span-7 space-y-3">
          <span className="text-xs font-mono text-slate-300 block">
            Grid Heatmap (Home vs Away goals)
          </span>

          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse" aria-label="Scoreline Heatmap">
              <thead>
                <tr>
                  <th className="p-2 text-slate-400 border border-slate-800 bg-slate-950 font-normal">
                    {homeTeamName.slice(0, 4)} \ {awayTeamName.slice(0, 4)}
                  </th>
                  {[0, 1, 2, 3].map((awayGoals) => (
                    <th key={awayGoals} className="p-2 text-slate-400 border border-slate-800 bg-slate-950 font-medium">
                      {awayGoals} Away
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.map((row, homeGoals) => (
                  <tr key={homeGoals}>
                    <th className="p-2 text-slate-400 border border-slate-800 bg-slate-950 font-medium text-left">
                      {homeGoals} Home
                    </th>
                    {row.map((cell) => {
                      const intensity = Math.min(1, cell.probability / maxProb);
                      const isTop = topScore && topScore.score === cell.score;

                      return (
                        <td
                          key={cell.score}
                          className="p-2.5 text-center border border-slate-800 transition-colors cursor-pointer group relative"
                          style={{
                            backgroundColor: `rgba(16, 185, 129, ${Math.max(0.04, intensity * 0.45)})`,
                          }}
                          title={`Scoreline ${cell.score}: ${formatProbability(cell.probability, 3)} (Exact: ${cell.probability})`}
                        >
                          <div className="flex flex-col items-center justify-center">
                            <span
                              className={`font-semibold ${
                                isTop ? 'text-emerald-300 underline font-bold' : 'text-slate-200'
                              }`}
                            >
                              {formatProbability(cell.probability)}
                            </span>
                            <span className="text-[9px] text-slate-400 font-mono">
                              {cell.score}
                            </span>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 pt-1">
            <span>Required 16-score mass: {formatProbability(correctScore.required_16_mass)}</span>
            <span>Tail mass (&gt;3 goals): {formatProbability(correctScore.tail_mass)}</span>
            <span>Sum: {correctScore.probability_sum !== undefined ? correctScore.probability_sum?.toFixed(4) : '1.000'}</span>
          </div>
        </div>

        {/* Top Scores Ranking List */}
        <div className="lg:col-span-5 space-y-3">
          <span className="text-xs font-mono text-slate-300 block">
            Ranked Top Scorelines
          </span>

          <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
            {topScores.map((item, idx) => {
              const isFirst = idx === 0;
              return (
                <div
                  key={item.score}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs font-mono ${
                    isFirst
                      ? 'bg-emerald-950/30 border-emerald-800/60 text-emerald-300'
                      : 'bg-slate-900/60 border-slate-800 text-slate-300'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="w-4 text-slate-500 font-bold">{idx + 1}.</span>
                    <span className="font-bold text-slate-100">{item.score}</span>
                    {isFirst && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-900/60 text-emerald-300">
                        Highest
                      </span>
                    )}
                  </div>
                  <div className="text-right font-semibold">
                    {formatProbability(item.probability, 2)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
};
