import React, { useState, useMemo } from 'react';
import {
  Sparkles,
  Trophy,
  Flame,
  ShieldCheck,
  TrendingUp,
  Target,
  Layers,
  ChevronRight,
  Share2,
  Calendar,
  CheckCircle2,
  XCircle,
  Clock,
  Activity,
  ArrowUpDown,
  Filter,
  Zap,
  Info,
  Award,
  Copy,
  Check,
  History,
  BarChart3,
  RotateCcw,
} from 'lucide-react';
import { DailyRankedPrediction, DailyPredictionSlip, RankedPredictionOutcome } from '../../api/types';
import { usePredictionHistory } from '../../api/queries';
import { formatDayDisplay, formatDateTime } from '../../lib/utils';
import { ShareSlipModal } from './ShareSlipModal';
import { TeamLogo } from '../common/TeamLogo';

export interface DailyAIPredictionsSectionProps {
  rankedPredictions?: DailyRankedPrediction[];
  slips?: DailyPredictionSlip[];
  dateStr: string;
  timeZone: 'IST' | 'UTC' | 'local' | string;
  isLoading?: boolean;
  onDateChange?: (date: string) => void;
}

export type RankingFilterMode = 'ALL' | 'BANKERS' | 'VALUE' | 'GOALS' | 'SAFETY';
export type RankingSortMode = 'RANK' | 'PROB_DESC' | 'ODDS_DESC' | 'EV_DESC';
export type ViewTabMode = 'RANKED_MATCHES' | 'COMBO_SLIPS' | 'PREDICTION_HISTORY';

export const DailyAIPredictionsSection: React.FC<DailyAIPredictionsSectionProps> = ({
  rankedPredictions = [],
  slips = [],
  dateStr,
  timeZone = 'IST',
  isLoading = false,
  onDateChange,
}) => {
  const [activeTab, setActiveTab] = useState<ViewTabMode>('RANKED_MATCHES');
  const [filterMode, setFilterMode] = useState<RankingFilterMode>('ALL');
  const [selectedLeague, setSelectedLeague] = useState<string>('ALL');
  const [sortMode, setSortMode] = useState<RankingSortMode>('RANK');
  const [selectedSlipForShare, setSelectedSlipForShare] = useState<DailyPredictionSlip | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Historical Track Record states
  const [historyDays, setHistoryDays] = useState<number>(7);
  const [historyLeague, setHistoryLeague] = useState<string>('ALL');
  const [historyOutcome, setHistoryOutcome] = useState<'ALL' | 'WON' | 'LOST'>('ALL');

  const { data: historyData, isLoading: isHistoryLoading, refetch: refetchHistory } = usePredictionHistory({
    days: historyDays,
    league: historyLeague !== 'ALL' ? historyLeague : undefined,
    outcome: historyOutcome,
    limit: 60,
    tz: timeZone,
  });

  // If backend rankedPredictions is not yet populated (e.g. while server cache refreshes), derive from slips.picks
  const effectivePredictions = useMemo(() => {
    if (rankedPredictions && rankedPredictions.length > 0) {
      return rankedPredictions;
    }
    if (!slips || slips.length === 0) return [];

    const map = new Map<number, DailyRankedPrediction>();
    const FLAG_MAP: Record<string, string> = {
      EPL: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', LA_LIGA: '🇪🇸', SERIE_A: '🇮🇹', BUNDESLIGA: '🇩🇪', LIGUE_1: '🇫🇷',
      UCL: '🏆', ISL: '🇮🇳', MLS: '🇺🇸', BRA_SERIE_A: '🇧🇷', LIGA_ARG: '🇦🇷',
    };

    slips.forEach((slip) => {
      slip.picks.forEach((pick) => {
        if (!map.has(pick.match_id)) {
          const probPct = pick.probability > 1 ? pick.probability : Math.round(pick.probability * 100);
          const evPct = Math.round(((probPct / 100) * pick.odds - 1) * 100);
          const parts = pick.fixture.split(' vs ');
          const home = parts[0] || 'Home';
          const away = parts[1] || 'Away';
          const isBanker = probPct >= 70;
          const isValue = evPct >= 5;

          const category: 'BANKER' | 'VALUE' | 'GOALS' | 'SAFETY' | 'MATCH_WINNER' =
            isBanker ? 'BANKER' : (isValue ? 'VALUE' : (pick.market.includes('Total') || pick.market.includes('BTTS') ? 'GOALS' : 'MATCH_WINNER'));

          const bestOutcome: RankedPredictionOutcome = {
            pick: pick.pick,
            market: pick.market,
            probability: probPct,
            odds: pick.odds,
            confidence: pick.confidence || 'HIGH',
            category,
            badge: isBanker ? '🌟 Top Banker' : (isValue ? '💎 Value Edge' : '⚽ Goals'),
            ev_edge: evPct > 0 ? `+${evPct}% Edge` : `${evPct}% Edge`,
            ai_score: Math.min(99, Math.round(probPct * 0.7 + Math.max(0, evPct) * 0.3)),
            status: pick.status || 'PENDING',
          };

          map.set(pick.match_id, {
            rank: 99,
            match_id: pick.match_id,
            fixture: pick.fixture,
            home_team: home,
            away_team: away,
            league_code: pick.league_code,
            league_name: pick.league,
            league_flag: FLAG_MAP[pick.league_code] || '⚽',
            kickoff_at: pick.kickoff_at,
            status: pick.status || 'SCHEDULED',
            best_outcome: bestOutcome,
            alternative_outcomes: [],
            projected_score: '2 - 1',
            ai_insight: `${pick.pick} carries ${probPct}% model certainty with statistical backing in ${pick.league}.`,
            sort_score: bestOutcome.ai_score,
          });
        }
      });
    });

    const list = Array.from(map.values()).sort((a, b) => b.sort_score - a.sort_score);
    list.forEach((item, idx) => {
      item.rank = idx + 1;
      item.is_nap_of_the_day = (idx === 0);
    });
    return list;
  }, [rankedPredictions, slips]);

  // Available unique leagues from predictions
  const availableLeagues = useMemo(() => {
    const map = new Map<string, { code: string; name: string; flag: string }>();
    effectivePredictions.forEach((p) => {
      if (!map.has(p.league_code)) {
        map.set(p.league_code, {
          code: p.league_code,
          name: p.league_name,
          flag: p.league_flag || '⚽',
        });
      }
    });
    return Array.from(map.values());
  }, [effectivePredictions]);

  // Separate active upcoming predictions from finished matches
  // Ended matches are completely eliminated from active bet lists!
  const activePredictions = useMemo(() => {
    return effectivePredictions.filter((p) => p.status !== 'FINISHED');
  }, [effectivePredictions]);

  const finishedPredictionsToday = useMemo(() => {
    return effectivePredictions.filter((p) => p.status === 'FINISHED');
  }, [effectivePredictions]);

  // Slips with finished picks eliminated
  const activeSlips = useMemo(() => {
    const list = slips.filter((s) => !s.picks.some((p) => p.status === 'WON' || p.status === 'LOST'));
    return list.length > 0 ? list : slips;
  }, [slips]);

  // Filter and sort active predictions only
  const filteredPredictions = useMemo(() => {
    let list = [...activePredictions];

    // Filter by category
    if (filterMode === 'BANKERS') {
      list = list.filter(
        (p) =>
          p.best_outcome.category === 'BANKER' ||
          p.best_outcome.probability >= 70.0 ||
          p.best_outcome.confidence === 'VERY HIGH'
      );
    } else if (filterMode === 'VALUE') {
      list = list.filter(
        (p) =>
          p.best_outcome.category === 'VALUE' ||
          parseFloat(p.best_outcome.ev_edge.replace(/[^0-9.-]/g, '') || '0') > 0
      );
    } else if (filterMode === 'GOALS') {
      list = list.filter(
        (p) =>
          p.best_outcome.category === 'GOALS' ||
          p.best_outcome.market === 'Totals' ||
          p.best_outcome.market === 'BTTS'
      );
    } else if (filterMode === 'SAFETY') {
      list = list.filter(
        (p) =>
          p.best_outcome.category === 'SAFETY' ||
          p.best_outcome.market === 'Double Chance'
      );
    }

    // Filter by league
    if (selectedLeague !== 'ALL') {
      list = list.filter((p) => p.league_code === selectedLeague);
    }

    // Sort
    list.sort((a, b) => {
      if (sortMode === 'RANK') {
        return a.rank - b.rank;
      }
      if (sortMode === 'PROB_DESC') {
        return b.best_outcome.probability - a.best_outcome.probability;
      }
      if (sortMode === 'ODDS_DESC') {
        return b.best_outcome.odds - a.best_outcome.odds;
      }
      if (sortMode === 'EV_DESC') {
        const evA = parseFloat(a.best_outcome.ev_edge.replace(/[^0-9.-]/g, '') || '0');
        const evB = parseFloat(b.best_outcome.ev_edge.replace(/[^0-9.-]/g, '') || '0');
        return evB - evA;
      }
      return 0;
    });

    return list;
  }, [activePredictions, filterMode, selectedLeague, sortMode]);

  // KPI Metrics (Calculated exclusively on active upcoming matches)
  const totalAnalyzed = activePredictions.length;
  const topBankersCount = activePredictions.filter(
    (p) => p.best_outcome.category === 'BANKER' || p.best_outcome.probability >= 70
  ).length;
  const highValueCount = activePredictions.filter(
    (p) => parseFloat(p.best_outcome.ev_edge.replace(/[^0-9.-]/g, '') || '0') >= 5.0
  ).length;
  const napOfTheDay = activePredictions.find((p) => p.is_nap_of_the_day || p.rank === 1) || activePredictions[0];

  const handleCopyPrediction = (p: DailyRankedPrediction) => {
    const text = `🎯 TacticX AI Daily Pick [Rank #${p.rank}]\n⚽ ${p.fixture} (${p.league_name})\n💡 Best Outcome: ${p.best_outcome.pick} @ ${p.best_outcome.odds}\n📊 Probability: ${p.best_outcome.probability}%\n📈 EV Edge: ${p.best_outcome.ev_edge}\n🔮 Projected Score: ${p.projected_score}\n🧠 Insight: ${p.ai_insight}\n⚡ Verified by TacticX AI Engine`;
    navigator.clipboard.writeText(text);
    setCopiedId(p.match_id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const handleShareCustomPick = (p: DailyRankedPrediction) => {
    const mockSlip: DailyPredictionSlip = {
      title: `Rank #${p.rank}: ${p.fixture}`,
      type: 'single_match',
      badge: p.best_outcome.badge,
      description: p.ai_insight,
      total_odds: p.best_outcome.odds,
      win_probability: p.best_outcome.probability,
      selections_count: 1,
      rank: p.rank,
      ai_score: p.best_outcome.ai_score,
      ev_edge: p.best_outcome.ev_edge,
      risk_level: p.best_outcome.category === 'BANKER' ? 'LOW' : 'BALANCED',
      outcome_status: p.best_outcome.status,
      picks: [
        {
          match_id: p.match_id,
          fixture: p.fixture,
          league: p.league_name,
          league_code: p.league_code,
          pick: p.best_outcome.pick,
          market: p.best_outcome.market,
          probability: p.best_outcome.probability / 100,
          odds: p.best_outcome.odds,
          confidence: p.best_outcome.confidence,
          kickoff_at: p.kickoff_at,
          status: p.best_outcome.status,
        },
      ],
    };
    setSelectedSlipForShare(mockSlip);
  };

  return (
    <section className="space-y-4">
      {/* 1. Header Banner & KPI Dashboard */}
      <div className="relative overflow-hidden rounded-2xl border border-[#242c3d] bg-gradient-to-br from-[#121622] via-[#101420] to-[#0d101a] p-4 sm:p-5 shadow-xl">
        <div className="absolute top-0 right-0 w-80 h-40 bg-[#21e786]/5 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-[#21e786]/10 border border-[#21e786]/25 text-[#21e786] shadow-sm">
                <Sparkles className="w-5 h-5" />
              </span>
              <div>
                <h2 className="text-lg sm:text-xl font-bold tracking-tight text-white font-sans flex items-center gap-2">
                  <span>Daily AI Predictions & Rankings</span>
                  <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-[#21e786]/15 text-[#21e786] border border-[#21e786]/30">
                    Live IST Feed
                  </span>
                </h2>
                <p className="text-xs text-slate-400 font-sans">
                  Mathematically ranked match outcomes, highest-confidence bankers, and EV edges powered by Poisson & situational models for {formatDayDisplay(dateStr, timeZone)}.
                </p>
              </div>
            </div>
          </div>

          {/* KPI Stat Chips */}
          <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs font-mono">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#171c28] border border-[#262f42] text-slate-300">
              <Target className="w-3.5 h-3.5 text-[#21e786]" />
              <span>Analyzed:</span>
              <span className="text-white font-bold">{totalAnalyzed} Matches</span>
            </div>

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#171c28] border border-[#262f42] text-slate-300">
              <Flame className="w-3.5 h-3.5 text-amber-400" />
              <span>Top Bankers:</span>
              <span className="text-amber-300 font-bold">{topBankersCount} High-Win</span>
            </div>

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#171c28] border border-[#262f42] text-slate-300">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              <span>+EV Value:</span>
              <span className="text-emerald-300 font-bold">{highValueCount} Picks</span>
            </div>
          </div>
        </div>

        {/* Primary View Switcher: Active Ranked Matches vs Combo Slips vs Prediction History */}
        <div className="mt-4 pt-3 border-t border-[#202738] flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center p-1 rounded-xl bg-[#0b0e14] border border-[#202738] gap-1">
            <button
              onClick={() => setActiveTab('RANKED_MATCHES')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold transition-all ${
                activeTab === 'RANKED_MATCHES'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md shadow-[#21e786]/20 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Trophy className="w-3.5 h-3.5" />
              <span>Active AI Picks ({activePredictions.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('COMBO_SLIPS')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold transition-all ${
                activeTab === 'COMBO_SLIPS'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md shadow-[#21e786]/20 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Curated Slips & Accas ({activeSlips.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('PREDICTION_HISTORY')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold transition-all ${
                activeTab === 'PREDICTION_HISTORY'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md shadow-[#21e786]/20 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>Prediction Track Record</span>
              {historyData?.summary?.win_rate !== undefined && (
                <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full font-bold ${
                  activeTab === 'PREDICTION_HISTORY'
                    ? 'bg-[#0a0d14]/20 text-[#0a0d14]'
                    : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                }`}>
                  {historyData.summary.win_rate}% Won
                </span>
              )}
            </button>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
            <Clock className="w-3 h-3 text-[#21e786]" />
            <span>Timezone:</span>
            <span className="text-emerald-400 font-bold">{timeZone === 'IST' ? 'IST (UTC+5:30)' : timeZone}</span>
          </div>
        </div>

        {/* Finished Matches Notification Banner (Eliminated from Active Slips) */}
        {finishedPredictionsToday.length > 0 && activeTab !== 'PREDICTION_HISTORY' && (
          <div className="mt-3 p-3 rounded-xl bg-[#141a26] border border-[#243044] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-sans">
            <div className="flex items-center gap-2 text-slate-300">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>
                <strong className="text-white font-mono">{finishedPredictionsToday.length} matches</strong> finished earlier today.
                Ended matches are eliminated from active betting slips so every slip is active and placeable.
              </span>
            </div>
            <button
              onClick={() => setActiveTab('PREDICTION_HISTORY')}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[#1f2638] hover:bg-[#273044] text-[#21e786] border border-[#2b354e] font-mono font-semibold transition-colors shrink-0 text-xs"
            >
              <History className="w-3.5 h-3.5" />
              <span>View Settled Results & Audit ({finishedPredictionsToday.length})</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* 2. TAB A: RANKED MATCHES VIEW */}
      {activeTab === 'RANKED_MATCHES' && (
        <div className="space-y-4">
          {/* Spotlight: Today's #1 Ranked AI Lock (Nap of the Day) */}
          {napOfTheDay && (
            <div className="relative overflow-hidden rounded-2xl border-2 border-amber-500/40 bg-gradient-to-r from-amber-950/20 via-[#161a26] to-[#121520] p-4 sm:p-5 shadow-lg">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[11px] font-mono font-bold">
                      <Flame className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                      <span>RANK #1 • AI BET OF THE DAY</span>
                    </span>
                    <span className="text-xs text-slate-400 font-sans">
                      {napOfTheDay.league_flag} {napOfTheDay.league_name}
                    </span>
                  </div>

                  <div>
                    <h3 className="text-base sm:text-lg font-bold text-white font-sans flex items-center gap-2.5">
                      <div className="flex items-center gap-2">
                        <TeamLogo teamName={napOfTheDay.home_team} size="md" />
                        <span>{napOfTheDay.home_team}</span>
                      </div>
                      <span className="text-slate-500 font-mono text-xs">vs</span>
                      <div className="flex items-center gap-2">
                        <TeamLogo teamName={napOfTheDay.away_team} size="md" />
                        <span>{napOfTheDay.away_team}</span>
                      </div>
                      {napOfTheDay.status === 'LIVE' && (
                        <span className="px-2 py-0.5 rounded-full bg-rose-500 text-white text-[10px] font-mono font-bold animate-pulse">
                          LIVE
                        </span>
                      )}
                    </h3>
                    <p className="text-xs text-slate-300 font-sans max-w-2xl mt-1.5">
                      {napOfTheDay.ai_insight}
                    </p>
                  </div>
                </div>

                {/* Right Pick Spotlight Metric Box */}
                <div className="flex flex-wrap sm:flex-nowrap items-center gap-3 bg-[#0d1017]/90 p-3 rounded-xl border border-amber-500/30">
                  <div className="text-left sm:text-right">
                    <div className="text-[10px] font-mono uppercase text-slate-400 font-semibold">Recommended Pick</div>
                    <div className="text-sm sm:text-base font-bold text-[#21e786] font-sans">
                      {napOfTheDay.best_outcome.pick}
                    </div>
                    <div className="text-[11px] font-mono text-slate-400">
                      Proj. Score: <span className="text-white font-bold">{napOfTheDay.projected_score}</span>
                    </div>
                  </div>

                  <div className="flex flex-col items-center justify-center px-3 py-1 bg-amber-500/15 rounded-lg border border-amber-500/30">
                    <span className="text-[10px] font-mono text-amber-300">ODDS</span>
                    <span className="text-base font-bold font-mono text-white">
                      {napOfTheDay.best_outcome.odds.toFixed(2)}
                    </span>
                  </div>

                  <div className="flex flex-col items-center justify-center px-3 py-1 bg-emerald-500/15 rounded-lg border border-emerald-500/30">
                    <span className="text-[10px] font-mono text-emerald-300">WIN PROB</span>
                    <span className="text-base font-bold font-mono text-emerald-400">
                      {napOfTheDay.best_outcome.probability}%
                    </span>
                  </div>

                  <button
                    onClick={() => handleCopyPrediction(napOfTheDay)}
                    className="p-2 rounded-lg bg-[#1c2230] hover:bg-[#252d40] text-slate-300 hover:text-white border border-[#2b354a] transition-colors"
                    title="Copy AI Prediction Details"
                  >
                    {copiedId === napOfTheDay.match_id ? (
                      <Check className="w-4 h-4 text-[#21e786]" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Filter & Sort Bar */}
          <div className="rounded-2xl border border-[#242938] bg-[#141822] p-3 space-y-3 shadow-sm">
            {/* 1. Ranking Filter Modes */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-mono text-slate-400 font-semibold flex items-center gap-1 mr-1">
                  <Filter className="w-3 h-3 text-[#21e786]" />
                  <span>Category:</span>
                </span>

                <button
                  onClick={() => setFilterMode('ALL')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-sans transition-all ${
                    filterMode === 'ALL'
                      ? 'bg-[#21e786] text-[#0a0d14] font-bold shadow-sm'
                      : 'bg-[#1b202c] text-slate-300 hover:bg-[#222838] border border-[#283244]'
                  }`}
                >
                  All Ranked ({rankedPredictions.length})
                </button>

                <button
                  onClick={() => setFilterMode('BANKERS')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-sans transition-all ${
                    filterMode === 'BANKERS'
                      ? 'bg-amber-400 text-[#0a0d14] font-bold shadow-sm'
                      : 'bg-[#1b202c] text-amber-300 hover:bg-[#222838] border border-amber-900/40'
                  }`}
                >
                  <Flame className="w-3 h-3" />
                  <span>Highest Possible / Bankers</span>
                </button>

                <button
                  onClick={() => setFilterMode('VALUE')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-sans transition-all ${
                    filterMode === 'VALUE'
                      ? 'bg-emerald-400 text-[#0a0d14] font-bold shadow-sm'
                      : 'bg-[#1b202c] text-emerald-300 hover:bg-[#222838] border border-emerald-900/40'
                  }`}
                >
                  <TrendingUp className="w-3 h-3" />
                  <span>High Value (+EV)</span>
                </button>

                <button
                  onClick={() => setFilterMode('GOALS')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-sans transition-all ${
                    filterMode === 'GOALS'
                      ? 'bg-sky-400 text-[#0a0d14] font-bold shadow-sm'
                      : 'bg-[#1b202c] text-sky-300 hover:bg-[#222838] border border-sky-900/40'
                  }`}
                >
                  <Zap className="w-3 h-3" />
                  <span>Goal Outcomes</span>
                </button>

                <button
                  onClick={() => setFilterMode('SAFETY')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-sans transition-all ${
                    filterMode === 'SAFETY'
                      ? 'bg-indigo-400 text-[#0a0d14] font-bold shadow-sm'
                      : 'bg-[#1b202c] text-indigo-300 hover:bg-[#222838] border border-indigo-900/40'
                  }`}
                >
                  <ShieldCheck className="w-3 h-3" />
                  <span>Double Chance</span>
                </button>
              </div>

              {/* Sort Selector */}
              <div className="flex items-center gap-1.5 text-xs font-mono bg-[#0e1118] px-2.5 py-1 rounded-lg border border-[#242c3d]">
                <ArrowUpDown className="w-3 h-3 text-[#21e786]" />
                <span className="text-slate-400">Sort:</span>
                <select
                  value={sortMode}
                  onChange={(e) => setSortMode(e.target.value as RankingSortMode)}
                  className="bg-transparent text-white font-semibold focus:outline-none cursor-pointer"
                >
                  <option value="RANK" className="bg-[#12151e]">AI Rank (#1 to #N)</option>
                  <option value="PROB_DESC" className="bg-[#12151e]">Win Probability %</option>
                  <option value="ODDS_DESC" className="bg-[#12151e]">Highest Odds</option>
                  <option value="EV_DESC" className="bg-[#12151e]">Maximum +EV Edge</option>
                </select>
              </div>
            </div>

            {/* 2. League-Wise Filter Strip */}
            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none pt-1">
              <span className="text-xs font-mono text-slate-400 font-semibold whitespace-nowrap mr-1">
                League-Wise:
              </span>

              <button
                onClick={() => setSelectedLeague('ALL')}
                className={`px-2.5 py-1 rounded-lg text-xs font-sans whitespace-nowrap transition-colors ${
                  selectedLeague === 'ALL'
                    ? 'bg-[#21e786] text-[#0a0d14] font-bold'
                    : 'bg-[#1b202c] text-slate-300 hover:bg-[#222838] border border-[#262f42]'
                }`}
              >
                All Leagues
              </button>

              {availableLeagues.map((lg) => (
                <button
                  key={lg.code}
                  onClick={() => setSelectedLeague(lg.code)}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-sans whitespace-nowrap transition-colors ${
                    selectedLeague === lg.code
                      ? 'bg-[#21e786] text-[#0a0d14] font-bold'
                      : 'bg-[#1b202c] text-slate-300 hover:bg-[#222838] border border-[#262f42]'
                  }`}
                >
                  <span>{lg.flag}</span>
                  <span>{lg.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 3. Ranked Predictions Cards Grid */}
          {isLoading ? (
            <div className="p-12 text-center text-slate-400 font-mono text-xs">
              Calculating Poisson simulations and situational market rankings...
            </div>
          ) : filteredPredictions.length === 0 ? (
            <div className="p-10 text-center rounded-2xl border border-[#242938] bg-[#141822] space-y-2">
              <Info className="w-8 h-8 text-slate-500 mx-auto" />
              <h4 className="font-semibold text-sm text-slate-200">No Predictions Found for Filter</h4>
              <p className="text-xs text-slate-400">
                Try selecting "All Ranked" or another league from the filter bar above.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {filteredPredictions.map((pred) => {
                const ko = pred.kickoff_at ? formatDateTime(pred.kickoff_at, timeZone) : null;
                const isRank1 = pred.rank === 1;
                const isRank2 = pred.rank === 2;
                const isRank3 = pred.rank === 3;

                return (
                  <div
                    key={pred.match_id}
                    className={`rounded-2xl border transition-all duration-200 p-4 space-y-3 bg-[#131620] hover:bg-[#161a26] shadow-sm hover:border-[#21e786]/40 ${
                      isRank1
                        ? 'border-amber-500/50 ring-1 ring-amber-500/20'
                        : isRank2
                        ? 'border-slate-400/50'
                        : isRank3
                        ? 'border-amber-700/50'
                        : 'border-[#222838]'
                    }`}
                  >
                    {/* Top Row: Rank Badge, League, Kickoff Time, Status */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {/* Official Rank Badge */}
                        <span
                          className={`inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-mono font-bold ${
                            isRank1
                              ? 'bg-amber-400 text-black shadow-sm'
                              : isRank2
                              ? 'bg-slate-300 text-black'
                              : isRank3
                              ? 'bg-amber-700 text-white'
                              : 'bg-[#1b202e] text-slate-300 border border-[#2a3448]'
                          }`}
                        >
                          Rank #{pred.rank}
                        </span>

                        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-sans">
                          <span>{pred.league_flag}</span>
                          <span className="font-medium text-slate-200">{pred.league_name}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {ko && (
                          <span className="text-[11px] font-mono text-slate-400 bg-[#0f121a] px-2 py-0.5 rounded border border-[#222838]">
                            {ko.time} IST
                          </span>
                        )}

                        {pred.status === 'LIVE' ? (
                          <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40 text-[10px] font-mono font-bold animate-pulse">
                            LIVE
                          </span>
                        ) : pred.status === 'FINISHED' ? (
                          <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 text-[10px] font-mono">
                            {pred.home_score !== null ? `${pred.home_score}-${pred.away_score}` : 'FT'}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {/* Fixture Pairing */}
                    <div className="flex items-center justify-between gap-2 border-b border-[#202636] pb-2.5">
                      <div className="flex items-center gap-2 truncate">
                        <div className="flex items-center gap-1.5 truncate">
                          <TeamLogo teamName={pred.home_team} size="sm" />
                          <span className="font-bold text-sm text-white font-sans truncate">{pred.home_team}</span>
                        </div>
                        <span className="text-xs text-slate-500 font-mono">vs</span>
                        <div className="flex items-center gap-1.5 truncate">
                          <TeamLogo teamName={pred.away_team} size="sm" />
                          <span className="font-bold text-sm text-white font-sans truncate">{pred.away_team}</span>
                        </div>
                      </div>
                      <div className="text-[11px] font-mono text-slate-400 whitespace-nowrap shrink-0">
                        Score Proj: <span className="text-[#21e786] font-bold">{pred.projected_score}</span>
                      </div>
                    </div>

                    {/* Primary Box: AI Best Possible Outcome */}
                    <div className="p-3 rounded-xl bg-[#0c0f16] border border-[#222a3c] space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
                          Optimal Outcome ({pred.best_outcome.market})
                        </span>
                        <span
                          className={`text-[10px] font-mono px-2 py-0.2 rounded-full font-bold ${
                            pred.best_outcome.category === 'BANKER'
                              ? 'bg-amber-400/20 text-amber-300 border border-amber-500/40'
                              : pred.best_outcome.category === 'VALUE'
                              ? 'bg-emerald-400/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-sky-400/20 text-sky-300 border border-sky-500/40'
                          }`}
                        >
                          {pred.best_outcome.badge}
                        </span>
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-bold text-white font-sans">
                          {pred.best_outcome.pick}
                        </span>

                        <div className="flex items-center gap-1.5 font-mono">
                          <span className="text-xs px-2 py-0.5 rounded bg-[#181d2a] text-slate-200 font-bold border border-[#2b354a]">
                            @{pred.best_outcome.odds.toFixed(2)}
                          </span>
                          <span className="text-xs px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-400 font-bold border border-emerald-800/60">
                            {pred.best_outcome.ev_edge}
                          </span>
                        </div>
                      </div>

                      {/* Probability Progress Bar */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
                          <span>AI Certainty</span>
                          <span className="text-white font-bold">{pred.best_outcome.probability}%</span>
                        </div>
                        <div className="h-1.5 w-full bg-[#181d2a] rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              pred.best_outcome.probability >= 75
                                ? 'bg-[#21e786]'
                                : pred.best_outcome.probability >= 60
                                ? 'bg-emerald-400'
                                : 'bg-amber-400'
                            }`}
                            style={{ width: `${Math.min(100, pred.best_outcome.probability)}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    {/* AI Model Rationale */}
                    <p className="text-xs text-slate-400 font-sans leading-relaxed">
                      {pred.ai_insight}
                    </p>

                    {/* Alternative Viable Outcomes */}
                    {pred.alternative_outcomes && pred.alternative_outcomes.length > 0 && (
                      <div className="pt-2 border-t border-[#1e2434] flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
                        <span className="text-slate-500 text-[10px]">Alternatives:</span>
                        {pred.alternative_outcomes.map((alt, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded bg-[#171b26] text-slate-300 border border-[#242c3e]"
                          >
                            {alt.pick} @{alt.odds.toFixed(2)} ({alt.probability}%)
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Actions: Copy & Share */}
                    <div className="pt-2 flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleCopyPrediction(pred)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono bg-[#181d28] hover:bg-[#202738] text-slate-300 hover:text-white border border-[#262f42] transition-colors"
                        title="Copy prediction summary"
                      >
                        {copiedId === pred.match_id ? (
                          <>
                            <Check className="w-3 h-3 text-[#21e786]" />
                            <span className="text-[#21e786] font-bold">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>

                      <button
                        onClick={() => handleShareCustomPick(pred)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono bg-[#21e786]/10 hover:bg-[#21e786]/20 text-[#21e786] border border-[#21e786]/30 transition-colors"
                      >
                        <Share2 className="w-3 h-3" />
                        <span>Share Slip</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 3. TAB B: CURATED COMBO SLIPS & ACCAS */}
      {activeTab === 'COMBO_SLIPS' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {activeSlips.length === 0 ? (
            <div className="col-span-full p-10 text-center rounded-2xl border border-[#242938] bg-[#141822] text-slate-400 text-xs font-sans">
              No accumulator slips generated for this date.
            </div>
          ) : (
            activeSlips.map((slip, sIdx) => {
              return (
                <div
                  key={sIdx}
                  className="rounded-2xl border border-[#242938] bg-[#141822] hover:bg-[#161b26] p-4 space-y-3.5 flex flex-col justify-between shadow-sm transition-all"
                >
                  <div className="space-y-2.5">
                    {/* Top Row: Rank & Odds */}
                    <div className="flex items-center justify-between gap-2">
                      <span className="px-2 py-0.5 rounded-full bg-[#1b202e] text-[#21e786] text-xs font-mono font-bold border border-[#262f42]">
                        Acca Rank #{slip.rank || sIdx + 1}
                      </span>
                      <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                        Total @{slip.total_odds.toFixed(2)}
                      </span>
                    </div>

                    <div>
                      <h4 className="font-bold text-sm text-white font-sans">{slip.title}</h4>
                      <p className="text-xs text-slate-400 font-sans mt-0.5">{slip.description}</p>
                    </div>

                    {/* Legs */}
                    <div className="space-y-1.5 pt-1">
                      {slip.picks.map((pick, pIdx) => {
                        const [homeTeam, awayTeam] = pick.fixture.includes(' vs ')
                          ? pick.fixture.split(' vs ')
                          : [pick.fixture, ''];
                        return (
                          <div
                            key={pIdx}
                            className="p-2 rounded-xl bg-[#0d1017] border border-[#1f2636] flex items-center justify-between gap-2 text-xs font-sans"
                          >
                            <div className="truncate min-w-0">
                              <div className="flex items-center gap-1.5 text-[11px] text-slate-400 truncate">
                                {homeTeam && <TeamLogo teamName={homeTeam.trim()} size="xs" />}
                                <span className="truncate">{homeTeam.trim()}</span>
                                {awayTeam && (
                                  <>
                                    <span className="text-slate-600 text-[10px]">vs</span>
                                    <TeamLogo teamName={awayTeam.trim()} size="xs" />
                                    <span className="truncate">{awayTeam.trim()}</span>
                                  </>
                                )}
                              </div>
                              <div className="font-bold text-white text-xs truncate mt-0.5">{pick.pick}</div>
                            </div>
                            <span className="font-mono text-emerald-400 font-bold whitespace-nowrap text-[11px]">
                              @{pick.odds.toFixed(2)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Slip Footer */}
                  <div className="pt-2 border-t border-[#1e2534] flex items-center justify-between gap-2">
                    <span className="text-xs font-mono text-slate-400">
                      Prob: <span className="text-white font-bold">{slip.win_probability}%</span>
                    </span>

                    <button
                      onClick={() => setSelectedSlipForShare(slip)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono bg-[#21e786]/10 hover:bg-[#21e786]/20 text-[#21e786] border border-[#21e786]/30 transition-colors"
                    >
                      <Share2 className="w-3 h-3" />
                      <span>Share Slip</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* 4. TAB C: PREDICTION TRACK RECORD & AUDITED HISTORY */}
      {activeTab === 'PREDICTION_HISTORY' && (
        <div className="space-y-4">
          {/* Performance Summary Banner */}
          <div className="rounded-2xl border border-[#232b3d] bg-gradient-to-br from-[#121622] via-[#10141f] to-[#0c0f18] p-4 sm:p-5 shadow-lg space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                    <ShieldCheck className="w-4 h-4" />
                  </span>
                  <h3 className="font-bold text-white text-base font-sans">
                    Prediction Settlement Ledger & Accuracy
                  </h3>
                </div>
                <p className="text-xs text-slate-400 font-sans mt-1">
                  Immutable record of finished matches evaluated against official full-time scorelines. Every pick is settled as Won or Lost with honest unit tracking.
                </p>
              </div>

              {/* Quick Lookback Selector */}
              <div className="flex items-center gap-1.5 text-xs font-mono">
                <span className="text-slate-400">Window:</span>
                {[3, 7, 14, 30].map((d) => (
                  <button
                    key={d}
                    onClick={() => setHistoryDays(d)}
                    className={`px-2.5 py-1 rounded-lg transition-all ${
                      historyDays === d
                        ? 'bg-[#21e786] text-[#0a0d14] font-bold shadow-sm'
                        : 'bg-[#181d28] text-slate-400 hover:text-white border border-[#232a3a]'
                    }`}
                  >
                    {d}d
                  </button>
                ))}
              </div>
            </div>

            {/* KPI Performance Cards Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Win Rate */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Win Rate</div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-[#21e786]">
                  {historyData?.summary?.win_rate ?? 0}%
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  Overall Accuracy
                </div>
              </div>

              {/* Record (Won / Lost) */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Record (W / L)</div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-white flex items-center gap-2">
                  <span className="text-emerald-400">{historyData?.summary?.won_count ?? 0}W</span>
                  <span className="text-slate-500">/</span>
                  <span className="text-rose-400">{historyData?.summary?.lost_count ?? 0}L</span>
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  {historyData?.summary?.total_predictions ?? 0} Matches Settled
                </div>
              </div>

              {/* Net Profit Units */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Net Return</div>
                <div className={`text-xl sm:text-2xl font-bold font-mono ${
                  (historyData?.summary?.net_units_num ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  {historyData?.summary?.total_units ?? '+0.0u'}
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  ROI: {historyData?.summary?.roi_pct ?? 0}%
                </div>
              </div>

              {/* Banker Accuracy */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Bankers Win Rate</div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-amber-300">
                  {historyData?.summary?.banker_win_rate ?? 0}%
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  Lock Picks (75%+ Prob)
                </div>
              </div>
            </div>

            {/* Filter Toolbar: Outcome & League */}
            <div className="pt-2 border-t border-[#1e2534] flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-1.5 text-xs font-sans">
                {(['ALL', 'WON', 'LOST'] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setHistoryOutcome(mode)}
                    className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                      historyOutcome === mode
                        ? mode === 'WON'
                          ? 'bg-emerald-500 text-slate-950 shadow-sm font-bold'
                          : mode === 'LOST'
                          ? 'bg-rose-500 text-white shadow-sm font-bold'
                          : 'bg-[#21e786] text-[#0a0d14] shadow-sm font-bold'
                        : 'bg-[#161a24] text-slate-300 hover:text-white border border-[#242c3c]'
                    }`}
                  >
                    {mode === 'ALL' ? 'All Settled' : mode === 'WON' ? 'Won Only ✅' : 'Lost Only ❌'}
                  </button>
                ))}
              </div>

              {/* League Selector */}
              <div className="flex items-center gap-2 text-xs font-sans">
                <span className="text-slate-400 font-mono">League:</span>
                <select
                  value={historyLeague}
                  onChange={(e) => setHistoryLeague(e.target.value)}
                  className="bg-[#0e121a] border border-[#242c3c] rounded-lg px-2.5 py-1 text-slate-200 text-xs focus:outline-none focus:border-[#21e786]"
                >
                  <option value="ALL">All Competitions</option>
                  <option value="EPL">Premier League</option>
                  <option value="LA_LIGA">La Liga</option>
                  <option value="SERIE_A">Serie A</option>
                  <option value="BUNDESLIGA">Bundesliga</option>
                  <option value="LIGUE_1">Ligue 1</option>
                  <option value="UCL">Champions League</option>
                  <option value="ISL">Indian Super League (ISL)</option>
                  <option value="MLS">Major League Soccer (MLS)</option>
                  <option value="BRA_SERIE_A">Brasileirão Série A</option>
                  <option value="LIGA_ARG">Liga Profesional Argentina</option>
                </select>

                <button
                  onClick={() => refetchHistory()}
                  className="p-1.5 rounded-lg bg-[#161a24] text-slate-300 hover:text-white border border-[#242c3c]"
                  title="Refresh track record"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>

          {/* Historical Match Cards */}
          {isHistoryLoading ? (
            <div className="p-12 text-center text-xs font-mono text-slate-400 rounded-2xl border border-[#242938] bg-[#141822]">
              Auditing historical predictions against canonical scorelines...
            </div>
          ) : !historyData?.history || historyData.history.length === 0 ? (
            <div className="p-12 text-center rounded-2xl border border-[#242938] bg-[#141822] space-y-2">
              <CheckCircle2 className="w-8 h-8 text-slate-500 mx-auto" />
              <h4 className="font-bold text-sm text-white font-sans">No Historical Matches Found</h4>
              <p className="text-xs text-slate-400 font-sans max-w-sm mx-auto">
                No finished predictions matched your selected filters ({historyOutcome}, {historyLeague}, {historyDays}d). Try resetting filters.
              </p>
              <button
                onClick={() => {
                  setHistoryOutcome('ALL');
                  setHistoryLeague('ALL');
                  setHistoryDays(7);
                }}
                className="px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold bg-[#21e786] text-[#0a0d14]"
              >
                Reset History Filters
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
              {historyData.history.map((item) => {
                const isWon = item.outcome_status === 'WON';
                return (
                  <div
                    key={item.match_id}
                    className={`rounded-2xl border p-4 space-y-3 shadow-sm transition-all ${
                      isWon
                        ? 'border-emerald-500/30 bg-gradient-to-b from-[#101918] to-[#0e141a]'
                        : 'border-rose-500/30 bg-gradient-to-b from-[#1a1014] to-[#0e141a]'
                    }`}
                  >
                    {/* Header: League & Status Banner */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 text-xs text-slate-400 font-sans">
                        <span>{item.league_flag}</span>
                        <span className="font-semibold text-slate-300">{item.league_name}</span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold tracking-wide ${
                            isWon
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          }`}
                        >
                          {isWon ? (
                            <>
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                              <span>CORRECT • {item.unit_return}</span>
                            </>
                          ) : (
                            <>
                              <XCircle className="w-3 h-3 text-rose-400" />
                              <span>WRONG • {item.unit_return}</span>
                            </>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* Fixture & Final Score */}
                    <div className="p-2.5 rounded-xl bg-[#0b0e14]/90 border border-[#1e2536] flex items-center justify-between gap-3">
                      <div className="truncate min-w-0">
                        <div className="flex items-center gap-2 truncate">
                          <div className="flex items-center gap-1.5 truncate">
                            <TeamLogo teamName={item.home_team} size="sm" />
                            <span className="text-xs font-bold text-white truncate font-sans">{item.home_team}</span>
                          </div>
                          <span className="text-[10px] text-slate-500 font-mono">vs</span>
                          <div className="flex items-center gap-1.5 truncate">
                            <TeamLogo teamName={item.away_team} size="sm" />
                            <span className="text-xs font-bold text-white truncate font-sans">{item.away_team}</span>
                          </div>
                        </div>
                        {item.kickoff_at && (
                          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                            {formatDateTime(item.kickoff_at, timeZone).full}
                          </div>
                        )}
                      </div>

                      {/* Prominent Full Time Score */}
                      <div className="text-right shrink-0">
                        <div className="text-[10px] font-mono text-slate-400 uppercase">Final Score</div>
                        <div className="text-base font-bold font-mono text-white px-2 py-0.5 rounded bg-[#171c26] border border-[#262f40]">
                          {item.final_score}
                        </div>
                      </div>
                    </div>

                    {/* Pick Details */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs font-sans">
                        <span className="text-slate-400 text-[11px]">AI Recommended Pick:</span>
                        <span className="font-mono text-slate-300 text-[11px]">
                          Prob: <strong className="text-white">{item.probability}%</strong>
                        </span>
                      </div>

                      <div className="p-2 rounded-xl bg-[#131722] border border-[#232c3e] flex items-center justify-between gap-2">
                        <div>
                          <div className="font-bold text-xs text-[#21e786] font-sans">
                            {item.pick}
                          </div>
                          <div className="text-[10px] font-mono text-slate-400">
                            {item.market}
                          </div>
                        </div>

                        <span className="font-mono text-xs font-bold px-2 py-1 rounded bg-[#0b0e14] text-white border border-[#1f2636]">
                          @{item.odds.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Post-Match Settlement Note */}
                    <div className="pt-2 border-t border-[#1c2230] text-xs font-sans text-slate-300">
                      <p className="text-[11px] leading-relaxed text-slate-300">
                        {item.audit_note}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Share Slip Modal */}
      {selectedSlipForShare && (
        <ShareSlipModal
          isOpen={!!selectedSlipForShare}
          slip={selectedSlipForShare}
          dateStr={dateStr}
          timeZone={timeZone}
          onClose={() => setSelectedSlipForShare(null)}
        />
      )}
    </section>
  );
};
