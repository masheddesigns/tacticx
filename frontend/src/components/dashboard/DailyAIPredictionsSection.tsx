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
} from 'lucide-react';
import { DailyRankedPrediction, DailyPredictionSlip, RankedPredictionOutcome } from '../../api/types';
import { formatDayDisplay, formatDateTime } from '../../lib/utils';
import { ShareSlipModal } from './ShareSlipModal';

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
export type ViewTabMode = 'RANKED_MATCHES' | 'COMBO_SLIPS';

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

  // Available unique leagues from predictions
  const availableLeagues = useMemo(() => {
    const map = new Map<string, { code: string; name: string; flag: string }>();
    rankedPredictions.forEach((p) => {
      if (!map.has(p.league_code)) {
        map.set(p.league_code, {
          code: p.league_code,
          name: p.league_name,
          flag: p.league_flag || '⚽',
        });
      }
    });
    return Array.from(map.values());
  }, [rankedPredictions]);

  // Filter and sort ranked predictions
  const filteredPredictions = useMemo(() => {
    let list = [...rankedPredictions];

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
  }, [rankedPredictions, filterMode, selectedLeague, sortMode]);

  // KPI Metrics
  const totalAnalyzed = rankedPredictions.length;
  const topBankersCount = rankedPredictions.filter(
    (p) => p.best_outcome.category === 'BANKER' || p.best_outcome.probability >= 70
  ).length;
  const highValueCount = rankedPredictions.filter(
    (p) => parseFloat(p.best_outcome.ev_edge.replace(/[^0-9.-]/g, '') || '0') >= 5.0
  ).length;
  const napOfTheDay = rankedPredictions.find((p) => p.is_nap_of_the_day || p.rank === 1);

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

        {/* Primary View Switcher: Ranked Matches vs Combo Slips */}
        <div className="mt-4 pt-3 border-t border-[#202738] flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center p-1 rounded-xl bg-[#0b0e14] border border-[#202738]">
            <button
              onClick={() => setActiveTab('RANKED_MATCHES')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold transition-all ${
                activeTab === 'RANKED_MATCHES'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md shadow-[#21e786]/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Trophy className="w-3.5 h-3.5" />
              <span>Ranked Match Outcomes ({rankedPredictions.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('COMBO_SLIPS')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold transition-all ${
                activeTab === 'COMBO_SLIPS'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md shadow-[#21e786]/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Curated Accas & Slips ({slips.length})</span>
            </button>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
            <Clock className="w-3 h-3 text-[#21e786]" />
            <span>Timezone:</span>
            <span className="text-emerald-400 font-bold">{timeZone === 'IST' ? 'IST (UTC+5:30)' : timeZone}</span>
          </div>
        </div>
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
                    <h3 className="text-base sm:text-lg font-bold text-white font-sans flex items-center gap-2">
                      <span>{napOfTheDay.fixture}</span>
                      {napOfTheDay.status === 'LIVE' && (
                        <span className="px-2 py-0.5 rounded-full bg-rose-500 text-white text-[10px] font-mono font-bold animate-pulse">
                          LIVE
                        </span>
                      )}
                    </h3>
                    <p className="text-xs text-slate-300 font-sans max-w-2xl mt-1">
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
                      <div className="font-bold text-sm text-white font-sans truncate">
                        {pred.fixture}
                      </div>
                      <div className="text-[11px] font-mono text-slate-400 whitespace-nowrap">
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
          {slips.length === 0 ? (
            <div className="col-span-full p-10 text-center rounded-2xl border border-[#242938] bg-[#141822] text-slate-400 text-xs font-sans">
              No accumulator slips generated for this date.
            </div>
          ) : (
            slips.map((slip, sIdx) => {
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
                      {slip.picks.map((pick, pIdx) => (
                        <div
                          key={pIdx}
                          className="p-2 rounded-xl bg-[#0d1017] border border-[#1f2636] flex items-center justify-between gap-2 text-xs font-sans"
                        >
                          <div className="truncate">
                            <div className="text-[11px] text-slate-400 truncate">{pick.fixture}</div>
                            <div className="font-bold text-white text-xs truncate">{pick.pick}</div>
                          </div>
                          <span className="font-mono text-emerald-400 font-bold whitespace-nowrap text-[11px]">
                            @{pick.odds.toFixed(2)}
                          </span>
                        </div>
                      ))}
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
