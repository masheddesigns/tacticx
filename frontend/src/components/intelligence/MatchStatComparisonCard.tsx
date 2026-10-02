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

const getTeamInitials = (name?: string | null): string => {
  if (!name) return '??';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 3).toUpperCase();
};

const getTeamColorStyle = (name?: string | null): string => {
  if (!name) return 'bg-slate-800 text-slate-300 border-slate-700';
  const colors = [
    'bg-red-950/80 text-red-300 border-red-800/60',
    'bg-blue-950/80 text-blue-300 border-blue-800/60',
    'bg-emerald-950/80 text-emerald-300 border-emerald-800/60',
    'bg-amber-950/80 text-amber-300 border-amber-800/60',
    'bg-purple-950/80 text-purple-300 border-purple-800/60',
    'bg-cyan-950/80 text-cyan-300 border-cyan-800/60',
    'bg-indigo-950/80 text-indigo-300 border-indigo-800/60',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  return colors[Math.abs(hash) % colors.length];
};

export const MatchStatComparisonCard: React.FC<MatchStatComparisonCardProps> = ({
  comparison,
  isLoading,
  homeTeamName,
  awayTeamName,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  if (isLoading) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-2xl p-6 shadow-sm animate-pulse space-y-4">
        <div className="h-6 bg-slate-800 rounded w-1/3" />
        <div className="h-4 bg-slate-800 rounded w-2/3" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
          <div className="h-28 bg-slate-800/60 rounded-xl" />
          <div className="h-28 bg-slate-800/60 rounded-xl" />
        </div>
        <div className="space-y-3 pt-4">
          <div className="h-12 bg-slate-800/40 rounded-lg" />
          <div className="h-12 bg-slate-800/40 rounded-lg" />
          <div className="h-12 bg-slate-800/40 rounded-lg" />
        </div>
      </div>
    );
  }

  if (!comparison) {
    return null;
  }

  const {
    is_finished,
    is_live,
    has_score,
    actual_score,
    actual_possession,
    detailed_stats,
    accuracy_summary,
    mirofish_summary,
    comparisons = [],
  } = comparison;

  const home = homeTeamName || comparison.home_team?.name || 'Home';
  const away = awayTeamName || comparison.away_team?.name || 'Away';
  const homeInitials = getTeamInitials(home);
  const awayInitials = getTeamInitials(away);

  // Extract Home / Away numbers for comparative FotMob stat bars
  const extractStatNumbers = (metricKey: string): { h: number; a: number } | null => {
    // 1. Detailed stats from backend if present
    if (detailed_stats) {
      const ds = detailed_stats as Record<string, any>;
      if (metricKey === 'possession' && ds.possession?.home !== undefined && ds.possession?.home !== null) {
        return {
          h: parseFloat(String(ds.possession.home)),
          a: parseFloat(String(ds.possession.away ?? '50')),
        };
      }
      if (metricKey === 'shots_total' && ds.shots_total?.home !== undefined && ds.shots_total?.home !== null) {
        return { h: Number(ds.shots_total.home), a: Number(ds.shots_total.away ?? 0) };
      }
      if (metricKey === 'shots_on_target' && ds.shots_on_target?.home !== undefined && ds.shots_on_target?.home !== null) {
        return { h: Number(ds.shots_on_target.home), a: Number(ds.shots_on_target.away ?? 0) };
      }
      if (metricKey === 'corners' && ds.corners?.home !== undefined && ds.corners?.home !== null) {
        return { h: Number(ds.corners.home), a: Number(ds.corners.away ?? 0) };
      }
      if (metricKey === 'fouls' && ds.fouls?.home !== undefined && ds.fouls?.home !== null) {
        return { h: Number(ds.fouls.home), a: Number(ds.fouls.away ?? 0) };
      }
      if (metricKey === 'yellow_cards' && ds.yellow_cards?.home !== undefined && ds.yellow_cards?.home !== null) {
        return { h: Number(ds.yellow_cards.home), a: Number(ds.yellow_cards.away ?? 0) };
      }
      if (metricKey === 'red_cards' && ds.red_cards?.home !== undefined && ds.red_cards?.home !== null) {
        return { h: Number(ds.red_cards.home), a: Number(ds.red_cards.away ?? 0) };
      }
    }

    // 2. Direct possession fallback
    if (metricKey === 'possession' && actual_possession?.home) {
      return {
        h: parseFloat(String(actual_possession.home)),
        a: parseFloat(String(actual_possession.away ?? '50')),
      };
    }

    // 3. Fallback: Parse from comparisons actual string (e.g. "13 corners (Argentina: 12, Bolivia: 1)")
    const found = comparisons.find((c) => c.metric.toLowerCase().includes(metricKey.toLowerCase()));
    if (found && found.actual) {
      const match = found.actual.match(/:?\s*(\d+(?:\.\d+)?)[^,]*,\s*[^:]*:?\s*(\d+(?:\.\d+)?)/);
      if (match) {
        return { h: parseFloat(match[1]), a: parseFloat(match[2]) };
      }
    }

    return null;
  };

  const statList = [
    { key: 'possession', label: 'Ball Possession', unit: '%', isPct: true },
    { key: 'shots_total', label: 'Total Shots', unit: '', isPct: false },
    { key: 'shots_on_target', label: 'Shots on Target', unit: '', isPct: false },
    { key: 'corners', label: 'Corner Kicks', unit: '', isPct: false },
    { key: 'fouls', label: 'Fouls Committed', unit: '', isPct: false },
    { key: 'yellow_cards', label: 'Yellow Cards', unit: '', isPct: false },
    { key: 'red_cards', label: 'Red Cards', unit: '', isPct: false },
  ];

  // 3-Way Outcome Probabilities from 1X2 comparisons
  const winItem = comparisons.find((c) => c.metric === 'Win' || c.metric === 'Match Winner (1X2)');
  const drawItem = comparisons.find((c) => c.metric === 'Draw');
  const lossItem = comparisons.find((c) => c.metric === 'Loss');

  const categories = [
    'ALL',
    '1X2 & Chance',
    'Over / Under Goals',
    'Both Teams To Score',
    'Team Specials',
    'Half Markets',
    'Handicap & Parity',
    'Correct Score',
    'Situational Stats',
    'Discipline',
  ];

  const filteredComparisons = comparisons.filter((c) => {
    const matchesCategory = selectedCategory === 'ALL' || c.category === selectedCategory;
    const q = searchQuery.toLowerCase().trim();
    const matchesSearch =
      !q ||
      c.metric.toLowerCase().includes(q) ||
      c.category.toLowerCase().includes(q) ||
      (c.notes ? c.notes.toLowerCase().includes(q) : false);
    return matchesCategory && matchesSearch;
  });

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
    <div className="bg-surface-card border border-surface-border rounded-2xl p-5 sm:p-6 shadow-md space-y-6">
      {/* 1. Header Banner & Title */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-surface-border/80">
        <div>
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
              Match Original Data vs Engine & MiroFish AI Prediction
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl font-sans">
            Direct side-by-side verification: authentic recorded game results, goals, corners, shots, and cards compared against pre-match mathematical engine probabilities & qualitative MiroFish simulations.
          </p>
        </div>

        {/* Accuracy & Grade Badges */}
        <div className="flex items-center gap-3 shrink-0">
          {is_finished && accuracy_summary.accuracy_percentage !== null ? (
            <div className="flex items-center gap-2.5 bg-slate-900 border border-slate-800 px-3.5 py-2 rounded-xl shadow-inner">
              <div className="text-right">
                <div className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Prediction Accuracy</div>
                <div className="text-base font-bold text-emerald-400 font-mono">
                  {accuracy_summary.accuracy_percentage}%
                  <span className="text-xs text-slate-400 ml-1 font-normal font-sans">
                    ({accuracy_summary.correct_hits}/{accuracy_summary.total_evaluated})
                  </span>
                </div>
              </div>
              <div
                className={`px-2.5 py-1 rounded-lg text-xs font-bold font-mono ${
                  accuracy_summary.grade === 'EXCELLENT'
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                    : accuracy_summary.grade === 'GOOD'
                    ? 'bg-blue-950 text-blue-300 border border-blue-800'
                    : 'bg-amber-950 text-amber-300 border border-amber-800'
                }`}
              >
                {accuracy_summary.grade}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3.5 py-2 rounded-xl text-xs text-amber-400 font-mono">
              <Clock className="w-4 h-4 animate-spin" />
              <span>Pre-Match Projections Active</span>
            </div>
          )}
        </div>
      </div>

      {/* 2. FotMob Match Score & Overview Banner */}
      {is_finished && has_score && actual_score && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-slate-900/70 p-4 sm:p-5 rounded-xl border border-slate-800">
          {/* Actual Final Score */}
          <div className="flex flex-col justify-center items-center p-3.5 bg-slate-950/70 rounded-xl border border-slate-800">
            <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider">Verified Match Score</span>
            <div className="text-3xl font-black text-white mt-1 font-mono tracking-tight">
              {actual_score.home} - {actual_score.away}
            </div>
            <span className="text-xs text-emerald-400 font-semibold mt-0.5">
              {actual_score.home > actual_score.away
                ? `${home} Won`
                : actual_score.away > actual_score.home
                ? `${away} Won`
                : 'Match Drawn'}
            </span>
          </div>

          {/* Actual Ball Possession */}
          <div className="flex flex-col justify-center p-3.5 bg-slate-950/70 rounded-xl border border-slate-800">
            <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider text-center md:text-left">
              Ball Possession
            </span>
            {actual_possession && actual_possession.home && actual_possession.away ? (
              <div className="mt-1 space-y-1.5">
                <div className="flex justify-between text-xs font-bold text-slate-200 font-mono">
                  <span className="text-emerald-400">{home}: {actual_possession.home}%</span>
                  <span className="text-blue-400">{away}: {actual_possession.away}%</span>
                </div>
                <div className="h-2.5 w-full bg-slate-800 rounded-full overflow-hidden flex gap-0.5">
                  <div
                    className="bg-emerald-500 h-full rounded-l-full transition-all duration-500"
                    style={{ width: `${actual_possession.home}%` }}
                  />
                  <div
                    className="bg-blue-500 h-full rounded-r-full transition-all duration-500"
                    style={{ width: `${actual_possession.away}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-500 mt-2 font-mono text-center md:text-left">
                Official possession pending provider sync
              </div>
            )}
          </div>

          {/* Calibration / Brier Record */}
          <div className="flex flex-col justify-center p-3.5 bg-slate-950/70 rounded-xl border border-slate-800">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider">Calibration Score</span>
              <Shield className="w-3.5 h-3.5 text-emerald-400" />
            </div>
            <div className="text-lg font-bold text-slate-200 mt-1 font-mono">
              {accuracy_summary.brier_score !== null && accuracy_summary.brier_score !== undefined
                ? `Brier: ${accuracy_summary.brier_score.toFixed(4)}`
                : 'Calculated Post-Match'}
            </div>
            <span className="text-[11px] text-slate-400 mt-0.5 font-sans">
              Lower Brier score indicates superior probabilistic confidence.
            </span>
          </div>
        </div>
      )}

      {/* 3. FotMob Signature Head-to-Head Comparative Stat Bars */}
      <div className="bg-slate-900/80 rounded-2xl p-5 border border-slate-800 space-y-4">
        {/* Teams Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2.5 min-w-0">
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold font-mono border shrink-0 ${getTeamColorStyle(
                home
              )}`}
            >
              {homeInitials}
            </span>
            <span className="text-sm font-bold text-white truncate max-w-[120px] sm:max-w-[200px]" title={home}>
              {home}
            </span>
          </div>

          <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 font-semibold px-2 py-0.5 rounded bg-slate-950 border border-slate-800 shrink-0">
            Head-to-Head Match Stats
          </span>

          <div className="flex items-center gap-2.5 min-w-0 justify-end">
            <span className="text-sm font-bold text-white truncate max-w-[120px] sm:max-w-[200px] text-right" title={away}>
              {away}
            </span>
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold font-mono border shrink-0 ${getTeamColorStyle(
                away
              )}`}
            >
              {awayInitials}
            </span>
          </div>
        </div>

        {/* 3-Way Outcome Win / Draw / Loss Probability Ribbon */}
        {winItem && lossItem && (
          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span className="text-emerald-400 font-bold">
                {home} Win: {winItem.probability_pct ?? winItem.engine_predicted}%
                {winItem.decimal_odds && <span className="text-amber-400 ml-1">(@{winItem.decimal_odds.toFixed(2)})</span>}
              </span>
              {drawItem && (
                <span className="text-amber-300 font-bold">
                  Draw: {drawItem.probability_pct ?? drawItem.engine_predicted}%
                  {drawItem.decimal_odds && <span className="text-amber-400 ml-1">(@{drawItem.decimal_odds.toFixed(2)})</span>}
                </span>
              )}
              <span className="text-blue-400 font-bold">
                {away} Win: {lossItem.probability_pct ?? lossItem.engine_predicted}%
                {lossItem.decimal_odds && <span className="text-amber-400 ml-1">(@{lossItem.decimal_odds.toFixed(2)})</span>}
              </span>
            </div>
            <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex gap-0.5">
              <div
                className="bg-emerald-500 h-full rounded-l-full"
                style={{ width: `${winItem.probability_pct ?? 45}%` }}
                title={`${home} Win`}
              />
              {drawItem && (
                <div
                  className="bg-amber-400 h-full"
                  style={{ width: `${drawItem.probability_pct ?? 25}%` }}
                  title="Draw"
                />
              )}
              <div
                className="bg-blue-500 h-full rounded-r-full"
                style={{ width: `${lossItem.probability_pct ?? 30}%` }}
                title={`${away} Win`}
              />
            </div>
          </div>
        )}

        {/* Stat Bars List (FotMob Dual-Color Horizontal Bars) */}
        <div className="divide-y divide-slate-800/60 pt-1">
          {statList.map(({ key, label, unit, isPct }) => {
            const vals = extractStatNumbers(key);
            if (!vals) return null;

            const total = vals.h + vals.a;
            const hPct = total > 0 ? (vals.h / total) * 100 : 50;
            const aPct = total > 0 ? (vals.a / total) * 100 : 50;
            const hLeading = vals.h > vals.a;
            const aLeading = vals.a > vals.h;

            return (
              <div key={key} className="py-2.5 first:pt-1 space-y-1.5">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span
                    className={`w-14 text-left font-bold ${
                      hLeading ? 'text-emerald-400 font-extrabold text-sm' : 'text-slate-300'
                    }`}
                  >
                    {vals.h}
                    {unit}
                  </span>
                  <span className="text-slate-300 font-sans text-xs font-medium">{label}</span>
                  <span
                    className={`w-14 text-right font-bold ${
                      aLeading ? 'text-blue-400 font-extrabold text-sm' : 'text-slate-300'
                    }`}
                  >
                    {vals.a}
                    {unit}
                  </span>
                </div>
                <div className="h-2 w-full bg-slate-800/80 rounded-full overflow-hidden flex gap-0.5">
                  <div
                    className={`h-full transition-all duration-500 rounded-l-full ${
                      hLeading ? 'bg-emerald-500' : 'bg-emerald-600/70'
                    }`}
                    style={{ width: `${isPct ? vals.h : hPct}%` }}
                  />
                  <div
                    className={`h-full transition-all duration-500 rounded-r-full ${
                      aLeading ? 'bg-blue-500' : 'bg-blue-600/70'
                    }`}
                    style={{ width: `${isPct ? vals.a : aPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. Search and Category Filter Tabs */}
      <div className="space-y-3 border-b border-surface-border/60 pb-3">
        {/* User Guide Card for Normal Users */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 text-xs flex flex-wrap items-center justify-between gap-3 font-mono">
          <div className="flex items-center gap-2 text-slate-300">
            <Info className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              <strong className="text-white">FotMob Match Engine Guide:</strong> Look at{' '}
              <span className="text-emerald-400 font-bold">What To Choose</span> for clear analytical signals.
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-700">
              Strong Yes (&gt;65%)
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-700">
              Favored (&gt;50%)
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-700">
              Close Call (~45%)
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
              Unlikely (&lt;40%)
            </span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search metric (e.g. Win, Handicap, Over 2.5, Corners, 1st Half)..."
            className="w-full sm:max-w-md px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 font-mono transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="px-2.5 py-1.5 text-xs text-slate-400 hover:text-white font-mono bg-slate-800/80 rounded-lg shrink-0"
            >
              Clear
            </button>
          )}
          <span className="text-xs text-slate-500 font-mono sm:ml-auto">
            Showing {filteredComparisons.length} of {comparisons.length} metrics
          </span>
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-colors whitespace-nowrap ${
                selectedCategory === cat
                  ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/40 shadow-sm'
                  : 'bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              {cat === 'ALL' ? 'All Metrics' : cat}
            </button>
          ))}
        </div>
      </div>

      {/* 5. FotMob-Style 44+ Market Comparison Table */}
      <div className="overflow-x-auto rounded-xl border border-surface-border bg-slate-950/40">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-900 text-slate-400 font-mono text-[11px] border-b border-surface-border">
              <th className="py-3 px-4">Metric & Market</th>
              <th className="py-3 px-4 text-blue-400">Model Probability & Odds</th>
              <th className="py-3 px-4 text-emerald-400">What To Choose (Signal)</th>
              <th className="py-3 px-4 text-slate-300">Match Original Data (Actual)</th>
              <th className="py-3 px-4 text-amber-400">MiroFish AI Take</th>
              <th className="py-3 px-4 text-right">Verification</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border/60">
            {filteredComparisons.map((item, idx) => {
              const prob = item.probability_pct;
              const rec = item.recommendation;

              return (
                <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                  {/* Metric */}
                  <td className="py-3.5 px-4">
                    <div className="font-semibold text-white flex items-center gap-1.5">
                      {item.metric}
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 uppercase mt-0.5">
                      {item.category} • {item.notes}
                    </div>
                  </td>

                  {/* Engine Predicted (Probability & European Decimal Odds) */}
                  <td className="py-3.5 px-4 font-mono font-medium text-slate-200">
                    <div className="space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-slate-100">
                          {prob !== undefined ? `${prob}%` : item.engine_predicted}
                        </span>
                        {item.decimal_odds && (
                          <span className="text-[11px] text-amber-400 font-semibold">
                            Odds: {item.decimal_odds.toFixed(2)}
                          </span>
                        )}
                      </div>
                      {prob !== undefined && (
                        <div className="w-28 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              prob >= 65
                                ? 'bg-emerald-400'
                                : prob >= 50
                                ? 'bg-blue-400'
                                : prob >= 40
                                ? 'bg-amber-400'
                                : 'bg-rose-400'
                            }`}
                            style={{ width: `${Math.min(100, prob)}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </td>

                  {/* What to Choose (Recommendation / Signal) */}
                  <td className="py-3.5 px-4 font-mono">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold border ${
                        rec === 'HIGH_CONFIDENCE'
                          ? 'bg-emerald-950/90 text-emerald-300 border-emerald-700/80'
                          : rec === 'LEAN_YES'
                          ? 'bg-blue-950/90 text-blue-300 border-blue-700/80'
                          : rec === 'TOSS_UP'
                          ? 'bg-amber-950/90 text-amber-300 border-amber-700/80'
                          : rec === 'LEAN_NO'
                          ? 'bg-rose-950/80 text-rose-300 border-rose-800/80'
                          : 'bg-slate-900 text-slate-400 border-slate-800'
                      }`}
                    >
                      {item.user_choice || (prob && prob >= 50 ? 'Favored' : 'Unlikely')}
                    </span>
                  </td>

                  {/* Match Original Data (Actual) */}
                  <td className="py-3.5 px-4 font-mono font-medium">
                    <span
                      className={`px-2 py-1 rounded inline-block ${
                        is_finished || is_live
                          ? 'bg-slate-900 text-slate-100 font-bold border border-slate-800'
                          : 'text-slate-500 italic'
                      }`}
                    >
                      {item.actual}
                    </span>
                  </td>

                  {/* MiroFish AI Predicted */}
                  <td className="py-3.5 px-4 text-slate-300">
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <Sparkles className="w-3 h-3 text-amber-400 flex-shrink-0" />
                      <span>{item.mirofish_predicted || 'Simulated scenario'}</span>
                    </div>
                  </td>

                  {/* Verification Status & Delta */}
                  <td className="py-3.5 px-4 text-right">
                    <div className="flex flex-col items-end gap-1">
                      {getStatusBadge(item.status)}
                      {item.delta && item.delta !== '-' && (
                        <span className="text-[10px] font-mono text-slate-400">
                          {item.delta}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 6. MiroFish Qualitative Simulation Takeaway */}
      {mirofish_summary && mirofish_summary.narrative && (
        <div className="bg-amber-950/20 border border-amber-900/40 rounded-xl p-4 flex items-start gap-3">
          <Sparkles className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold text-amber-300 font-mono uppercase tracking-wider mr-2">
              MiroFish Scenario Intelligence:
            </span>
            <span className="text-amber-200/90 leading-relaxed font-sans">
              {mirofish_summary.narrative}
            </span>
          </div>
        </div>
      )}

      {/* 7. Transparency Footer */}
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
