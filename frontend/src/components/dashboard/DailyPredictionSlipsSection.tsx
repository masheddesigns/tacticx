import React, { useState, useMemo } from 'react';
import {
  Ticket,
  ShieldCheck,
  Zap,
  TrendingUp,
  Flame,
  CheckCircle2,
  XCircle,
  Clock,
  Activity,
  ChevronRight,
  Sparkles,
  Share2,
  Flag,
  Target,
  Trophy,
  Award,
  ArrowUpDown,
  Filter,
  Layers,
  RotateCcw,
  Calendar,
} from 'lucide-react';
import { DailyPredictionSlip } from '../../api/types';
import { formatDayDisplay } from '../../lib/utils';
import { ShareSlipModal } from './ShareSlipModal';

export interface DailyPredictionSlipsSectionProps {
  slips: DailyPredictionSlip[];
  dateStr: string;
  timeZone: 'UTC' | 'local' | string;
  isLoading?: boolean;
  onDateChange?: (date: string) => void;
}

export type SlipFilterType =
  | 'ALL'
  | 'SINGLE'
  | 'MULTI'
  | 'HIGH_WIN'
  | 'HIGH_ODDS'
  | 'WON'
  | 'LOST'
  | 'PENDING';

export type SlipSortType =
  | 'RANK'
  | 'ODDS_DESC'
  | 'WIN_DESC'
  | 'EV_DESC'
  | 'ODDS_ASC';

export const DailyPredictionSlipsSection: React.FC<DailyPredictionSlipsSectionProps> = ({
  slips,
  dateStr,
  timeZone,
  isLoading,
  onDateChange,
}) => {
  const [selectedSlipForShare, setSelectedSlipForShare] = useState<DailyPredictionSlip | null>(null);
  const [activeFilter, setActiveFilter] = useState<SlipFilterType>('ALL');
  const [activeSort, setActiveSort] = useState<SlipSortType>('RANK');

  // Filter and sort slips
  const filteredAndSortedSlips = useMemo(() => {
    if (!slips) return [];
    let list = [...slips];

    // Filter
    if (activeFilter === 'SINGLE') {
      list = list.filter((s) => s.is_single_match || s.selections_count === 1 || s.type === 'single_match');
    } else if (activeFilter === 'MULTI') {
      list = list.filter((s) => !s.is_single_match && s.selections_count > 1);
    } else if (activeFilter === 'HIGH_WIN') {
      list = list.filter((s) => s.win_probability >= 75);
    } else if (activeFilter === 'HIGH_ODDS') {
      list = list.filter((s) => s.total_odds >= 2.0);
    } else if (activeFilter === 'WON') {
      list = list.filter((s) => s.outcome_status === 'WON');
    } else if (activeFilter === 'LOST') {
      list = list.filter((s) => s.outcome_status === 'LOST');
    } else if (activeFilter === 'PENDING') {
      list = list.filter((s) => s.outcome_status === 'PENDING' || s.outcome_status === 'LIVE');
    }

    // Sort
    list.sort((a, b) => {
      if (activeSort === 'RANK') {
        return (a.rank ?? 99) - (b.rank ?? 99);
      }
      if (activeSort === 'ODDS_DESC') {
        return b.total_odds - a.total_odds;
      }
      if (activeSort === 'WIN_DESC') {
        return b.win_probability - a.win_probability;
      }
      if (activeSort === 'EV_DESC') {
        const evA = parseFloat(a.ev_edge?.replace(/[^0-9.-]/g, '') || '0');
        const evB = parseFloat(b.ev_edge?.replace(/[^0-9.-]/g, '') || '0');
        return evB - evA;
      }
      if (activeSort === 'ODDS_ASC') {
        return a.total_odds - b.total_odds;
      }
      return 0;
    });

    return list;
  }, [slips, activeFilter, activeSort]);

  // Counts for filter pills
  const counts = useMemo(() => {
    if (!slips) return { all: 0, single: 0, multi: 0, highWin: 0, highOdds: 0, won: 0, lost: 0, pending: 0 };
    return {
      all: slips.length,
      single: slips.filter((s) => s.is_single_match || s.selections_count === 1 || s.type === 'single_match').length,
      multi: slips.filter((s) => !s.is_single_match && s.selections_count > 1).length,
      highWin: slips.filter((s) => s.win_probability >= 75).length,
      highOdds: slips.filter((s) => s.total_odds >= 2.0).length,
      won: slips.filter((s) => s.outcome_status === 'WON').length,
      lost: slips.filter((s) => s.outcome_status === 'LOST').length,
      pending: slips.filter((s) => s.outcome_status === 'PENDING' || s.outcome_status === 'LIVE').length,
    };
  }, [slips]);

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-[#242938] bg-[#161922] p-6 animate-pulse space-y-4">
        <div className="h-5 w-48 bg-slate-800 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="h-52 bg-slate-800/50 rounded-xl" />
          <div className="h-52 bg-slate-800/50 rounded-xl" />
          <div className="h-52 bg-slate-800/50 rounded-xl" />
        </div>
      </div>
    );
  }

  if (!slips || slips.length === 0) {
    return null;
  }

  const getSlipIcon = (type: string) => {
    switch (type) {
      case 'banker':
        return <ShieldCheck className="w-4 h-4 text-[#21e786]" />;
      case 'accumulator':
        return <Zap className="w-4 h-4 text-amber-400" />;
      case 'corners_cards':
        return <Flag className="w-4 h-4 text-purple-400" />;
      case 'goals':
        return <Flame className="w-4 h-4 text-rose-400" />;
      case 'value':
        return <TrendingUp className="w-4 h-4 text-emerald-400" />;
      case 'mega':
        return <Sparkles className="w-4 h-4 text-cyan-400" />;
      case 'single_match':
        return <Target className="w-4 h-4 text-[#21e786]" />;
      default:
        return <Ticket className="w-4 h-4 text-blue-400" />;
    }
  };

  const getSlipBorder = (type: string) => {
    switch (type) {
      case 'banker':
        return 'border-[#21e786]/30 hover:border-[#21e786]/60 shadow-[0_0_15px_rgba(33,231,134,0.06)]';
      case 'accumulator':
        return 'border-amber-400/30 hover:border-amber-400/60 shadow-[0_0_15px_rgba(251,191,36,0.06)]';
      case 'corners_cards':
        return 'border-purple-400/30 hover:border-purple-400/60 shadow-[0_0_15px_rgba(192,132,252,0.06)]';
      case 'goals':
        return 'border-rose-400/30 hover:border-rose-400/60 shadow-[0_0_15px_rgba(244,63,94,0.06)]';
      case 'value':
        return 'border-emerald-400/30 hover:border-emerald-400/60 shadow-[0_0_15px_rgba(52,211,153,0.06)]';
      case 'mega':
        return 'border-cyan-400/30 hover:border-cyan-400/60 shadow-[0_0_15px_rgba(34,211,238,0.06)]';
      case 'single_match':
        return 'border-[#21e786]/30 hover:border-[#21e786]/60 shadow-[0_0_15px_rgba(33,231,134,0.06)]';
      default:
        return 'border-[#242938] hover:border-slate-700';
    }
  };

  const renderOutcomeBadge = (status?: string) => {
    switch (status) {
      case 'WON':
        return (
          <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-[#21e786] border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3 text-[#21e786]" />
            <span>WON</span>
          </span>
        );
      case 'LOST':
        return (
          <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3 h-3 text-rose-400" />
            <span>LOST</span>
          </span>
        );
      case 'LIVE':
        return (
          <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
            <Activity className="w-3 h-3 text-amber-400 animate-pulse" />
            <span>LIVE</span>
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-[#1e222e] text-slate-400 border border-[#242938]">
            <Clock className="w-3 h-3 text-slate-400" />
            <span>UPCOMING</span>
          </span>
        );
    }
  };

  return (
    <div className="rounded-2xl border border-[#242938] bg-[#161922] p-5 sm:p-6 space-y-5 shadow-sm">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#242938]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#21e786]/10 border border-[#21e786]/20 flex items-center justify-center text-[#21e786]">
            <Ticket className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-white font-sans flex items-center gap-2">
                <span>Daily AI Prediction Slips</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[#21e786]/20 text-[#21e786] border border-[#21e786]/30">
                  Parimatch Aligned
                </span>
              </h2>
            </div>
            <p className="text-xs text-slate-400 font-sans mt-0.5">
              Ranked AI betting slips with single match bets, accumulators & projected match statistics for {formatDayDisplay(dateStr, timeZone)}.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {onDateChange && (
            <div className="flex items-center gap-1.5 bg-[#0e1015] px-2.5 py-1 rounded-lg border border-[#242938]">
              <Calendar className="w-3.5 h-3.5 text-[#21e786]" />
              <input
                type="date"
                value={dateStr}
                min="2026-10-01"
                max="2026-11-05"
                onChange={(e) => {
                  if (e.target.value) {
                    onDateChange(e.target.value);
                  }
                }}
                className="bg-transparent text-xs text-slate-200 font-sans focus:outline-none cursor-pointer [color-scheme:dark]"
                title="Select date for daily prediction slips"
              />
            </div>
          )}

          <span className="text-[11px] font-mono text-[#21e786] bg-[#21e786]/10 px-2.5 py-1 rounded-md border border-[#21e786]/20 font-bold">
            {slips.length} Slips Available
          </span>
        </div>
      </div>

      {/* Interactive Controls: Filter Tabs & Sort Dropdown */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3 rounded-xl bg-[#0e1015] border border-[#242938]">
        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto pb-1 lg:pb-0 scrollbar-none">
          <span className="text-[11px] font-mono text-slate-500 uppercase mr-1 flex items-center gap-1">
            <Filter className="w-3 h-3" /> Filter:
          </span>
          <button
            onClick={() => setActiveFilter('ALL')}
            className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
              activeFilter === 'ALL'
                ? 'bg-[#21e786] text-[#0e1015] shadow-sm font-bold'
                : 'bg-[#161922] text-slate-300 hover:text-white border border-[#242938]'
            }`}
          >
            <span>All</span>
            <span className="text-[10px] font-mono opacity-80">({counts.all})</span>
          </button>

          <button
            onClick={() => setActiveFilter('SINGLE')}
            className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
              activeFilter === 'SINGLE'
                ? 'bg-[#21e786] text-[#0e1015] shadow-sm font-bold'
                : 'bg-[#161922] text-slate-300 hover:text-white border border-[#242938]'
            }`}
          >
            <Target className="w-3 h-3" />
            <span>Single Matches</span>
            <span className="text-[10px] font-mono opacity-80">({counts.single})</span>
          </button>

          <button
            onClick={() => setActiveFilter('MULTI')}
            className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
              activeFilter === 'MULTI'
                ? 'bg-[#21e786] text-[#0e1015] shadow-sm font-bold'
                : 'bg-[#161922] text-slate-300 hover:text-white border border-[#242938]'
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>Multi-Leg Accas</span>
            <span className="text-[10px] font-mono opacity-80">({counts.multi})</span>
          </button>

          <button
            onClick={() => setActiveFilter('HIGH_WIN')}
            className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
              activeFilter === 'HIGH_WIN'
                ? 'bg-[#21e786] text-[#0e1015] shadow-sm font-bold'
                : 'bg-[#161922] text-slate-300 hover:text-white border border-[#242938]'
            }`}
          >
            <ShieldCheck className="w-3 h-3 text-[#21e786]" />
            <span>75%+ Win Prob</span>
            <span className="text-[10px] font-mono opacity-80">({counts.highWin})</span>
          </button>

          <button
            onClick={() => setActiveFilter('HIGH_ODDS')}
            className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
              activeFilter === 'HIGH_ODDS'
                ? 'bg-[#21e786] text-[#0e1015] shadow-sm font-bold'
                : 'bg-[#161922] text-slate-300 hover:text-white border border-[#242938]'
            }`}
          >
            <Zap className="w-3 h-3 text-amber-400" />
            <span>High Odds (2.0x+)</span>
            <span className="text-[10px] font-mono opacity-80">({counts.highOdds})</span>
          </button>

          {counts.won > 0 && (
            <button
              onClick={() => setActiveFilter('WON')}
              className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
                activeFilter === 'WON'
                  ? 'bg-emerald-400 text-[#0e1015] shadow-sm font-bold'
                  : 'bg-[#161922] text-emerald-300 hover:text-emerald-200 border border-emerald-500/30'
              }`}
            >
              <CheckCircle2 className="w-3 h-3 text-[#21e786]" />
              <span>Won Slips ({counts.won})</span>
            </button>
          )}

          {counts.lost > 0 && (
            <button
              onClick={() => setActiveFilter('LOST')}
              className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors flex items-center gap-1 ${
                activeFilter === 'LOST'
                  ? 'bg-rose-500 text-white shadow-sm font-bold'
                  : 'bg-[#161922] text-rose-300 hover:text-rose-200 border border-rose-500/30'
              }`}
            >
              <XCircle className="w-3 h-3 text-rose-400" />
              <span>Lost ({counts.lost})</span>
            </button>
          )}
        </div>

        {/* Sort Controls */}
        <div className="flex items-center gap-2 shrink-0">
          <label htmlFor="slip-sort-select" className="text-[11px] font-mono text-slate-400 flex items-center gap-1 whitespace-nowrap">
            <ArrowUpDown className="w-3 h-3 text-[#21e786]" /> Sort by:
          </label>
          <select
            id="slip-sort-select"
            value={activeSort}
            onChange={(e) => setActiveSort(e.target.value as SlipSortType)}
            className="bg-[#161922] border border-[#242938] text-slate-200 hover:text-white text-xs font-sans font-semibold rounded-lg px-2.5 py-1 focus:outline-none focus:ring-1 focus:ring-[#21e786] transition-colors cursor-pointer"
          >
            <option value="RANK">AI Rank (Top Recommended)</option>
            <option value="ODDS_DESC">Highest Odds (Most Multiplier)</option>
            <option value="WIN_DESC">Highest Win Probability</option>
            <option value="EV_DESC">Best EV Model Edge</option>
            <option value="ODDS_ASC">Lowest Odds (Safest)</option>
          </select>
        </div>
      </div>

      {/* Slips Grid */}
      {filteredAndSortedSlips.length === 0 ? (
        <div className="p-8 text-center rounded-xl bg-[#0e1015] border border-[#242938] space-y-3">
          <Ticket className="w-8 h-8 text-slate-600 mx-auto" />
          <p className="text-sm text-slate-400 font-sans">
            No slips match the current filter selection.
          </p>
          <button
            onClick={() => setActiveFilter('ALL')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-sans font-semibold bg-[#1e222e] hover:bg-[#242938] text-white border border-[#242938] transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5 text-[#21e786]" />
            <span>Reset to All Slips</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {filteredAndSortedSlips.map((slip, idx) => (
            <div
              key={idx}
              className={`rounded-xl bg-[#0e1015] border p-4 flex flex-col justify-between transition-all space-y-4 ${getSlipBorder(
                slip.type
              )}`}
            >
              {/* Slip Header & AI Ranking Bar */}
              <div>
                <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-[#242938]">
                  <div className="flex items-center gap-2">
                    {/* Rank Badge */}
                    <div
                      className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-bold border ${
                        slip.rank === 1
                          ? 'bg-amber-400/20 text-amber-300 border-amber-400/40 shadow-[0_0_8px_rgba(251,191,36,0.2)]'
                          : slip.rank === 2
                          ? 'bg-slate-300/20 text-slate-200 border-slate-300/30'
                          : slip.rank === 3
                          ? 'bg-amber-600/20 text-amber-400 border-amber-600/30'
                          : 'bg-[#1e222e] text-slate-400 border-[#242938]'
                      }`}
                    >
                      {slip.rank && slip.rank <= 3 ? (
                        <Trophy className="w-3 h-3 text-amber-400 shrink-0" />
                      ) : (
                        <Award className="w-3 h-3 text-slate-400 shrink-0" />
                      )}
                      <span>#{slip.rank || idx + 1}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {getSlipIcon(slip.type)}
                      <h3 className="font-bold text-sm text-white font-sans truncate">{slip.title}</h3>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {renderOutcomeBadge(slip.outcome_status)}
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#1e222e] border border-[#242938] text-slate-300">
                      {slip.selections_count} {slip.selections_count === 1 ? 'Pick' : 'Picks'}
                    </span>
                  </div>
                </div>

                {/* Badges strip: EV Edge & Risk level */}
                <div className="flex items-center justify-between gap-2 mt-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {slip.ev_edge && (
                      <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-[#21e786]/10 text-[#21e786] border border-[#21e786]/20">
                        {slip.ev_edge}
                      </span>
                    )}
                    {slip.risk_level && (
                      <span
                        className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border ${
                          slip.risk_level === 'LOW'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : slip.risk_level === 'BALANCED'
                            ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        }`}
                      >
                        {slip.risk_level} Risk
                      </span>
                    )}
                    {slip.is_single_match && (
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                        Single Bet
                      </span>
                    )}
                  </div>

                  {slip.ai_score && (
                    <div className="text-[10px] font-mono text-slate-400 whitespace-nowrap">
                      AI Score: <strong className="text-white">{slip.ai_score}</strong>
                    </div>
                  )}
                </div>

                <p className="text-[11px] text-slate-400 font-sans mt-2 line-clamp-2">
                  {slip.description}
                </p>

                {/* Picks List */}
                <div className="space-y-2 mt-3.5">
                  {slip.picks.map((pick, pIdx) => (
                    <div
                      key={pIdx}
                      className="p-2.5 rounded-lg bg-[#161922] border border-[#242938] hover:border-slate-700 transition-colors flex flex-col gap-1.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-mono text-slate-400 truncate">
                              {pick.league}
                            </span>
                            <span className="text-[10px] text-slate-600">•</span>
                            <span className="text-[10px] font-mono font-semibold text-[#21e786]">
                              {Math.round(pick.probability * 100)}% Win
                            </span>
                          </div>
                          <div className="text-xs font-semibold text-slate-200 truncate mt-0.5">
                            {pick.fixture}
                          </div>
                          <div className="text-[11px] font-sans font-bold text-white mt-0.5 flex items-center gap-1">
                            {pick.status === 'WON' ? (
                              <CheckCircle2 className="w-3.5 h-3.5 text-[#21e786] shrink-0" />
                            ) : pick.status === 'LOST' ? (
                              <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                            ) : (
                              <CheckCircle2 className="w-3 h-3 text-[#21e786] shrink-0" />
                            )}
                            <span className="truncate">{pick.pick}</span>
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <div className="text-[10px] text-slate-400 font-sans">Odds</div>
                          <div className="text-xs font-mono font-bold text-[#21e786] bg-[#0e1015] px-2 py-1 rounded border border-[#242938] mt-0.5">
                            {pick.odds.toFixed(2)}
                          </div>
                        </div>
                      </div>

                      {/* Projected Stats Bar (Corners, Cards, Shots on Target) */}
                      {pick.projected_stats && (
                        <div className="flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-[#242938]/60 text-[10px] font-mono">
                          {pick.projected_stats.corners_total !== undefined && (
                            <div className="flex items-center gap-1 bg-[#0e1015] px-1.5 py-0.5 rounded border border-[#242938] text-purple-300">
                              <Flag className="w-2.5 h-2.5 text-purple-400" />
                              <span>~{pick.projected_stats.corners_total} Corn</span>
                              {pick.projected_stats.corners_home !== undefined && pick.projected_stats.corners_away !== undefined && (
                                <span className="text-slate-500 text-[9px]">({pick.projected_stats.corners_home}-{pick.projected_stats.corners_away})</span>
                              )}
                            </div>
                          )}
                          {pick.projected_stats.cards_total !== undefined && (
                            <div className="flex items-center gap-1 bg-[#0e1015] px-1.5 py-0.5 rounded border border-[#242938] text-amber-300">
                              <span className="w-2 h-2.5 bg-amber-400 rounded-[1px] inline-block shadow-[0_0_4px_rgba(251,191,36,0.5)]" />
                              <span>~{pick.projected_stats.cards_total} Cards</span>
                            </div>
                          )}
                          {pick.projected_stats.shots_on_target !== undefined && (
                            <div className="flex items-center gap-1 bg-[#0e1015] px-1.5 py-0.5 rounded border border-[#242938] text-cyan-300">
                              <Target className="w-2.5 h-2.5 text-cyan-400" />
                              <span>~{pick.projected_stats.shots_on_target} SoT</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Slip Summary / Total Odds Footer & Share Button */}
              <div className="pt-3 border-t border-[#242938] space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-[10px] text-slate-400 font-sans uppercase tracking-wider">
                      {slip.is_single_match ? 'Single Odds' : 'Combined Odds'}
                    </div>
                    <div className="text-lg font-black font-mono text-[#21e786]">
                      {slip.total_odds.toFixed(2)}x
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-[10px] text-slate-400 font-sans uppercase tracking-wider">
                      Win Probability
                    </div>
                    <div className="text-xs font-bold font-mono text-slate-200">
                      {slip.win_probability}%
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedSlipForShare(slip)}
                  className="w-full py-1.5 px-3 rounded-lg text-xs font-sans font-semibold bg-[#1e222e] hover:bg-[#242938] text-slate-200 hover:text-white border border-[#242938] transition-colors flex items-center justify-center gap-1.5 shadow-sm"
                >
                  <Share2 className="w-3.5 h-3.5 text-[#21e786]" />
                  <span>Share Slip Screenshot</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Share Slip Modal */}
      <ShareSlipModal
        isOpen={Boolean(selectedSlipForShare)}
        onClose={() => setSelectedSlipForShare(null)}
        slip={selectedSlipForShare}
        dateStr={dateStr}
        timeZone={timeZone}
      />
    </div>
  );
};
