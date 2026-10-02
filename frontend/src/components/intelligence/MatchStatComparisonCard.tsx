import React, { useState } from 'react';
import {
  Trophy,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  BarChart3,
  Flame,
  AlertTriangle,
  Info,
  Shield,
  Activity,
  ArrowRight,
} from 'lucide-react';
import { MatchStatComparisonResponse, ComparisonItem } from '../../api/types';

interface MatchStatComparisonCardProps {
  comparison?: MatchStatComparisonResponse;
  isLoading?: boolean;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const MatchStatComparisonCard: React.FC<MatchStatComparisonCardProps> = ({
  comparison,
  isLoading,
  homeTeamName,
  awayTeamName,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  if (isLoading) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-xl p-6 shadow-sm animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-800 rounded w-2/3 mb-6" />
        <div className="space-y-3">
          <div className="h-14 bg-slate-800/60 rounded" />
          <div className="h-14 bg-slate-800/60 rounded" />
          <div className="h-14 bg-slate-800/60 rounded" />
        </div>
      </div>
    );
  }

  if (!comparison) {
    return null;
  }

  const {
    is_finished,
    has_score,
    actual_score,
    actual_possession,
    accuracy_summary,
    mirofish_summary,
    comparisons = [],
  } = comparison;

  const home = homeTeamName || comparison.home_team?.name || 'Home';
  const away = awayTeamName || comparison.away_team?.name || 'Away';

  const categories = ['ALL', 'Outcome', 'Goals', 'Situational', 'Discipline', 'Markets'];
  const filteredComparisons = selectedCategory === 'ALL'
    ? comparisons
    : comparisons.filter((c) => c.category === selectedCategory);

  const getStatusBadge = (status: ComparisonItem['status']) => {
    switch (status) {
      case 'HIT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800/50">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Hit
          </span>
        );
      case 'CLOSE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-800/50">
            <Info className="w-3.5 h-3.5" />
            Within Margin
          </span>
        );
      case 'MISS':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800/50">
            <XCircle className="w-3.5 h-3.5" />
            Variance
          </span>
        );
      case 'AWAITING_SYNC':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            <Clock className="w-3.5 h-3.5" />
            Sync Pending
          </span>
        );
      case 'PENDING':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">
            <Clock className="w-3.5 h-3.5" />
            {is_finished ? 'Sync Pending' : 'Pending Kickoff'}
          </span>
        );
    }
  };

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 shadow-sm space-y-6">
      {/* 1. Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-surface-border/80">
        <div>
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-bold text-white tracking-tight">
              Match Original Data vs Engine & MiroFish AI Prediction
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Direct side-by-side verification: authentic recorded game results, goals, corners, shots, and cards compared against pre-match mathematical engine probabilities & qualitative MiroFish simulations.
          </p>
        </div>

        {/* Accuracy & Grade Badges */}
        <div className="flex items-center gap-3">
          {is_finished && accuracy_summary.accuracy_percentage !== null ? (
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3.5 py-2 rounded-xl">
              <div className="text-right">
                <div className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Prediction Accuracy</div>
                <div className="text-base font-bold text-emerald-400 font-mono">
                  {accuracy_summary.accuracy_percentage}%
                  <span className="text-xs text-slate-400 ml-1 font-normal font-sans">
                    ({accuracy_summary.correct_hits}/{accuracy_summary.total_evaluated})
                  </span>
                </div>
              </div>
              <div className={`px-2 py-1 rounded text-xs font-bold font-mono ${
                accuracy_summary.grade === 'EXCELLENT'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                  : accuracy_summary.grade === 'GOOD'
                  ? 'bg-blue-950 text-blue-300 border border-blue-800'
                  : 'bg-amber-950 text-amber-300 border border-amber-800'
              }`}>
                {accuracy_summary.grade}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl text-xs text-amber-400 font-mono">
              <Clock className="w-4 h-4 animate-spin" />
              <span>Pre-Match Projections Active</span>
            </div>
          )}
        </div>
      </div>

      {/* 2. Hero Scoreline & Match Overview */}
      {is_finished && has_score && actual_score && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800/80">
          {/* Actual Final Score */}
          <div className="flex flex-col justify-center items-center p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider">Verified Match Score</span>
            <div className="text-2xl font-black text-white mt-1 font-mono tracking-tight">
              {actual_score.home} - {actual_score.away}
            </div>
            <span className="text-xs text-emerald-400 font-medium mt-0.5">
              {actual_score.home > actual_score.away
                ? `${home} Won`
                : actual_score.away > actual_score.home
                ? `${away} Won`
                : 'Match Drawn'}
            </span>
          </div>

          {/* Actual Ball Possession (if recorded) */}
          <div className="flex flex-col justify-center p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider">Ball Possession</span>
            {actual_possession && actual_possession.home && actual_possession.away ? (
              <div className="mt-1 space-y-1.5">
                <div className="flex justify-between text-xs font-semibold text-slate-300 font-mono">
                  <span>{home}: {actual_possession.home}%</span>
                  <span>{away}: {actual_possession.away}%</span>
                </div>
                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex">
                  <div
                    className="bg-emerald-500 h-full"
                    style={{ width: `${actual_possession.home}%` }}
                  />
                  <div
                    className="bg-blue-500 h-full"
                    style={{ width: `${actual_possession.away}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-500 mt-2 font-mono">
                Official possession pending provider sync
              </div>
            )}
          </div>

          {/* Model Brier Evaluation Record */}
          <div className="flex flex-col justify-center p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider">Calibration Score</span>
              <Shield className="w-3.5 h-3.5 text-emerald-400" />
            </div>
            <div className="text-lg font-bold text-slate-200 mt-1 font-mono">
              {accuracy_summary.brier_score !== null && accuracy_summary.brier_score !== undefined
                ? `Brier: ${accuracy_summary.brier_score.toFixed(4)}`
                : 'Calculated Post-Match'}
            </div>
            <span className="text-[11px] text-slate-400 mt-0.5">
              Lower Brier score indicates superior probabilistic confidence.
            </span>
          </div>
        </div>
      )}

      {/* 3. Category Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-surface-border/50">
        <span className="text-xs text-slate-500 font-mono mr-2">Filter:</span>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-colors whitespace-nowrap ${
              selectedCategory === cat
                ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/30'
                : 'bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-slate-800'
            }`}
          >
            {cat === 'ALL' ? 'All Metrics' : cat}
          </button>
        ))}
      </div>

      {/* 4. Side-by-Side Comparison Table */}
      <div className="overflow-x-auto rounded-xl border border-surface-border">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-900/80 text-slate-400 font-mono text-[11px] border-b border-surface-border">
              <th className="py-3 px-4">Metric & Market</th>
              <th className="py-3 px-4 text-emerald-400">Match Original Data (Actual)</th>
              <th className="py-3 px-4 text-blue-400">Predictive Engine Model</th>
              <th className="py-3 px-4 text-amber-400">MiroFish AI Forecast</th>
              <th className="py-3 px-4">Delta / Variance</th>
              <th className="py-3 px-4 text-right">Verification</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border/60">
            {filteredComparisons.map((item, idx) => (
              <tr
                key={idx}
                className="hover:bg-slate-800/30 transition-colors"
              >
                {/* Metric */}
                <td className="py-3.5 px-4">
                  <div className="font-semibold text-white flex items-center gap-1.5">
                    {item.metric}
                  </div>
                  <div className="text-[10px] font-mono text-slate-500 uppercase mt-0.5">
                    {item.category} • {item.notes}
                  </div>
                </td>

                {/* Match Original Data (Actual) */}
                <td className="py-3.5 px-4 font-mono font-medium">
                  <span className={`px-2 py-1 rounded ${
                    is_finished
                      ? 'bg-slate-900 text-slate-100 font-bold border border-slate-800'
                      : 'text-slate-500 italic'
                  }`}>
                    {item.actual}
                  </span>
                </td>

                {/* Engine Predicted */}
                <td className="py-3.5 px-4 font-mono font-medium text-slate-200">
                  <div className="bg-slate-900/80 px-2 py-1 rounded border border-slate-800 inline-block">
                    {item.engine_predicted}
                  </div>
                </td>

                {/* MiroFish AI Predicted */}
                <td className="py-3.5 px-4 text-slate-300">
                  <div className="flex items-center gap-1 text-[11px]">
                    <Sparkles className="w-3 h-3 text-amber-400 flex-shrink-0" />
                    <span>{item.mirofish_predicted || 'Simulated flow'}</span>
                  </div>
                </td>

                {/* Delta / Difference */}
                <td className="py-3.5 px-4 font-mono text-slate-400">
                  <span className={`text-[11px] ${
                    item.status === 'HIT'
                      ? 'text-emerald-400 font-semibold'
                      : item.status === 'CLOSE'
                      ? 'text-amber-400'
                      : item.status === 'MISS'
                      ? 'text-rose-400'
                      : 'text-slate-500'
                  }`}>
                    {item.delta}
                  </span>
                </td>

                {/* Verification Status */}
                <td className="py-3.5 px-4 text-right">
                  {getStatusBadge(item.status)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 5. MiroFish Qualitative Simulation Takeaway */}
      {mirofish_summary && mirofish_summary.narrative && (
        <div className="bg-amber-950/20 border border-amber-900/40 rounded-xl p-4 flex items-start gap-3">
          <Sparkles className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold text-amber-300 font-mono uppercase tracking-wider mr-2">
              MiroFish Scenario Intelligence:
            </span>
            <span className="text-amber-200/90 leading-relaxed">
              {mirofish_summary.narrative}
            </span>
          </div>
        </div>
      )}

      {/* 6. Transparency Footer */}
      <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono pt-2">
        <div className="flex items-center gap-1.5">
          <Shield className="w-3.5 h-3.5 text-emerald-400" />
          <span>Immutable Pre-Match Cutoff Snapshot — Predictions frozen prior to kickoff</span>
        </div>
        <span>Phase 27 Canonical Verification</span>
      </div>
    </div>
  );
};
