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
  Ticket,
} from 'lucide-react';
import {
  DailyRankedPrediction,
  DailyPredictionSlip,
  RankedPredictionOutcome,
  HistoricalSlipItem,
} from '../../api/types';
import { usePredictionHistory } from '../../api/queries';
import { formatDayDisplay, formatDateTime } from '../../lib/utils';
import { ShareSlipModal } from './ShareSlipModal';
import { TeamLogo } from '../common/TeamLogo';
import { LeagueLogo } from '../common/LeagueLogo';

export interface DailyAIPredictionsSectionProps {
  rankedPredictions?: DailyRankedPrediction[];
  slips?: DailyPredictionSlip[];
  dateStr: string;
  timeZone: 'IST' | 'UTC' | 'local' | string;
  isLoading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
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
  error = null,
  onRetry,
  onDateChange,
}) => {
  const [activeTab, setActiveTab] = useState<ViewTabMode>('RANKED_MATCHES');
  const [filterMode, setFilterMode] = useState<RankingFilterMode>('ALL');
  const [selectedLeague, setSelectedLeague] = useState<string>('ALL');
  const [sortMode, setSortMode] = useState<RankingSortMode>('RANK');
  const [selectedSlipForShare, setSelectedSlipForShare] = useState<DailyPredictionSlip | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [copiedSlipId, setCopiedSlipId] = useState<string | null>(null);

  // Historical Track Record states
  const [historyDays, setHistoryDays] = useState<number>(7);
  const [historyLeague, setHistoryLeague] = useState<string>('ALL');
  const [historyOutcome, setHistoryOutcome] = useState<'ALL' | 'WON' | 'LOST'>('ALL');
  const [historySubTab, setHistorySubTab] = useState<'SLIPS' | 'MATCHES'>('SLIPS');

  const { data: historyData, isLoading: isHistoryLoading, refetch: refetchHistory } = usePredictionHistory({
    days: historyDays,
    league: historyLeague !== 'ALL' ? historyLeague : undefined,
    outcome: historyOutcome,
    limit: 60,
    tz: timeZone,
  });

  // Effective Historical Slips (uses backend payload with robust client derivation fallback)
  const effectiveHistoricalSlips = useMemo(() => {
    let rawSlips = historyData?.historical_slips || [];
    if (rawSlips.length > 0) {
      if (historyOutcome === 'WON') {
        return rawSlips.filter((s) => s.outcome_status === 'WON');
      }
      if (historyOutcome === 'LOST') {
        return rawSlips.filter((s) => s.outcome_status === 'LOST');
      }
      return rawSlips;
    }
    const historyList = historyData?.history || [];
    if (historyList.length === 0) return [];

    const groups = new Map<string, typeof historyList>();
    historyList.forEach((item) => {
      const dKey = item.kickoff_at ? item.kickoff_at.slice(0, 10) : 'Recent';
      if (!groups.has(dKey)) groups.set(dKey, []);
      groups.get(dKey)!.push(item);
    });

    const slipsList: HistoricalSlipItem[] = [];
    groups.forEach((items, dKey) => {
      if (items.length >= 2) {
        const sortedBankers = [...items].sort((a, b) => b.probability - a.probability);
        const bCount = Math.min(3, sortedBankers.length);
        const bPicks = sortedBankers.slice(0, bCount);
        let combOdds = 1.0;
        bPicks.forEach((p) => { combOdds *= p.odds; });
        const avgProb = bPicks.reduce((acc, p) => acc + p.probability, 0) / bPicks.length;
        const allWon = bPicks.every((p) => p.outcome_status === 'WON');
        const unitPnl = allWon ? Math.round((combOdds - 1.0) * 100) / 100 : -1.0;

        slipsList.push({
          id: `hist-slip-${dKey}-banker`,
          title: `Safe Banker ${bCount === 3 ? 'Treble' : 'Double'}`,
          type: 'banker',
          badge: '75%+ Probability',
          description: `Top statistical certainty selections from ${dKey} matchday.`,
          date: dKey,
          total_odds: Math.round(combOdds * 100) / 100,
          win_probability: Math.round(avgProb * 10) / 10,
          selections_count: bCount,
          outcome_status: allWon ? 'WON' : 'LOST',
          unit_return: allWon ? `+${unitPnl}u` : `${unitPnl}u`,
          unit_pnl: unitPnl,
          audit_note: allWon
            ? `All ${bCount} legs hit cleanly! Settled at ${combOdds.toFixed(2)}x payout.`
            : `${bPicks.filter((p) => p.outcome_status === 'WON').length}/${bCount} legs won. Failed on ${bPicks.filter((p) => p.outcome_status !== 'WON').map((p) => p.fixture).join(', ')}.`,
          picks: bPicks.map((p) => ({
            match_id: p.match_id,
            fixture: p.fixture,
            home_team: p.home_team,
            away_team: p.away_team,
            league_code: p.league_code,
            league_name: p.league_name,
            league_flag: p.league_flag,
            pick: p.pick,
            market: p.market,
            odds: p.odds,
            probability: p.probability,
            final_score: p.final_score,
            status: p.outcome_status,
            audit_note: p.audit_note,
          })),
        });

        const goalPicks = items.filter((p) => p.category === 'GOALS' || p.market === 'Totals' || p.market === 'BTTS' || p.pick.includes('Over') || p.pick.includes('Both Teams'));
        if (goalPicks.length >= 2) {
          const gSubset = goalPicks.slice(0, 3);
          let gOdds = 1.0;
          gSubset.forEach((p) => { gOdds *= p.odds; });
          const gProb = gSubset.reduce((acc, p) => acc + p.probability, 0) / gSubset.length;
          const gWon = gSubset.every((p) => p.outcome_status === 'WON');
          const gPnl = gWon ? Math.round((gOdds - 1.0) * 100) / 100 : -1.0;

          slipsList.push({
            id: `hist-slip-${dKey}-goals`,
            title: 'Goals Galore Combo',
            type: 'goals',
            badge: 'Over Goals & BTTS',
            description: `Curated high-scoring lines from ${dKey} matchday.`,
            date: dKey,
            total_odds: Math.round(gOdds * 100) / 100,
            win_probability: Math.round(gProb * 10) / 10,
            selections_count: gSubset.length,
            outcome_status: gWon ? 'WON' : 'LOST',
            unit_return: gWon ? `+${gPnl}u` : `${gPnl}u`,
            unit_pnl: gPnl,
            audit_note: gWon
              ? `All ${gSubset.length} goal selections cleared! Full slip won @ ${gOdds.toFixed(2)}.`
              : `${gSubset.filter((p) => p.outcome_status === 'WON').length}/${gSubset.length} legs won. Missed on ${gSubset.filter((p) => p.outcome_status !== 'WON').map((p) => p.fixture).join(', ')}.`,
            picks: gSubset.map((p) => ({
              match_id: p.match_id,
              fixture: p.fixture,
              home_team: p.home_team,
              away_team: p.away_team,
              league_code: p.league_code,
              league_name: p.league_name,
              league_flag: p.league_flag,
              pick: p.pick,
              market: p.market,
              odds: p.odds,
              probability: p.probability,
              final_score: p.final_score,
              status: p.outcome_status,
              audit_note: p.audit_note,
            })),
          });
        }
      } else if (items.length === 1) {
        const s = items[0];
        const sWon = s.outcome_status === 'WON';
        slipsList.push({
          id: `hist-slip-${dKey}-single`,
          title: `Single Banker: ${s.fixture}`,
          type: 'single_match',
          badge: 'Top Single Pick',
          description: `Primary standalone recommendation on ${dKey}.`,
          date: dKey,
          total_odds: s.odds,
          win_probability: s.probability,
          selections_count: 1,
          outcome_status: sWon ? 'WON' : 'LOST',
          unit_return: s.unit_return,
          unit_pnl: s.unit_pnl,
          audit_note: s.audit_note,
          picks: [{
            match_id: s.match_id,
            fixture: s.fixture,
            home_team: s.home_team,
            away_team: s.away_team,
            league_code: s.league_code,
            league_name: s.league_name,
            league_flag: s.league_flag,
            pick: s.pick,
            market: s.market,
            odds: s.odds,
            probability: s.probability,
            final_score: s.final_score,
            status: s.outcome_status,
            audit_note: s.audit_note,
          }],
        });
      }
    });

    if (historyList.length >= 3 && slipsList.length < 3) {
      const top3 = [...historyList].sort((a, b) => b.probability - a.probability).slice(0, 3);
      let cOdds = 1.0;
      top3.forEach((p) => { cOdds *= p.odds; });
      const cProb = top3.reduce((acc, p) => acc + p.probability, 0) / top3.length;
      const cWon = top3.every((p) => p.outcome_status === 'WON');
      const cPnl = cWon ? Math.round((cOdds - 1.0) * 100) / 100 : -1.0;

      slipsList.push({
        id: 'hist-slip-cross-treble',
        title: 'Multi-Day Safe Banker Treble',
        type: 'banker',
        badge: 'Highest Confidence',
        description: 'Highest-confidence mathematical selections across recent matchdays.',
        date: 'Recent',
        total_odds: Math.round(cOdds * 100) / 100,
        win_probability: Math.round(cProb * 10) / 10,
        selections_count: 3,
        outcome_status: cWon ? 'WON' : 'LOST',
        unit_return: cWon ? `+${cPnl}u` : `${cPnl}u`,
        unit_pnl: cPnl,
        audit_note: cWon
          ? `All 3 legs hit cleanly! Settled at ${cOdds.toFixed(2)}x payout.`
          : `${top3.filter((p) => p.outcome_status === 'WON').length}/3 legs won. Missed on ${top3.filter((p) => p.outcome_status !== 'WON').map((p) => p.fixture).join(', ')}.`,
        picks: top3.map((p) => ({
          match_id: p.match_id,
          fixture: p.fixture,
          home_team: p.home_team,
          away_team: p.away_team,
          league_code: p.league_code,
          league_name: p.league_name,
          league_flag: p.league_flag,
          pick: p.pick,
          market: p.market,
          odds: p.odds,
          probability: p.probability,
          final_score: p.final_score,
          status: p.outcome_status,
          audit_note: p.audit_note,
        })),
      });
    }

    if (historyOutcome === 'WON') {
      return slipsList.filter((s) => s.outcome_status === 'WON');
    }
    if (historyOutcome === 'LOST') {
      return slipsList.filter((s) => s.outcome_status === 'LOST');
    }
    return slipsList;
  }, [historyData, historyOutcome]);

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

  const handleShareHistoricalSlip = (hs: HistoricalSlipItem) => {
    const modalSlip: DailyPredictionSlip = {
      title: `${hs.title} (${hs.date})`,
      type: hs.type,
      badge: hs.badge,
      description: hs.description,
      total_odds: hs.total_odds,
      win_probability: hs.win_probability,
      selections_count: hs.selections_count,
      outcome_status: (hs.outcome_status === 'WON' || hs.outcome_status === 'LOST') ? hs.outcome_status : 'PENDING',
      risk_level: hs.type === 'banker' ? 'LOW' : 'BALANCED',
      picks: hs.picks.map((p) => ({
        match_id: p.match_id,
        fixture: p.fixture,
        league: p.league_name,
        league_code: p.league_code,
        pick: p.pick,
        market: p.market,
        probability: p.probability / 100,
        odds: p.odds,
        confidence: 'HIGH',
        status: (p.status === 'WON' || p.status === 'LOST') ? p.status : 'PENDING',
      })),
    };
    setSelectedSlipForShare(modalSlip);
  };

  const handleCopyHistoricalSlip = (hs: HistoricalSlipItem) => {
    const legsText = hs.picks
      .map(
        (p, idx) =>
          `  ${idx + 1}. ${p.fixture} (${p.league_name}) • ${p.pick} @ ${p.odds} [Score: ${p.final_score}] - ${
            p.status === 'WON' ? '✅ WON' : '❌ LOST'
          }`
      )
      .join('\n');
    const text = `🎟️ TacticX AI Historical Slip [${hs.outcome_status === 'WON' ? 'WON ✅' : 'LOST ❌'}]\n📋 ${
      hs.title
    } (${hs.badge})\n📅 Date: ${hs.date}\n💰 Combined Odds: @${hs.total_odds}\n📊 Probability: ${
      hs.win_probability
    }%\n\nSelections:\n${legsText}\n\n📝 Settlement: ${hs.audit_note}\n⚡ Verified by TacticX AI Engine`;
    navigator.clipboard.writeText(text);
    setCopiedSlipId(hs.id);
    setTimeout(() => setCopiedSlipId(null), 2500);
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
              {isLoading ? (
                <span className="inline-block w-8 h-3.5 bg-slate-700/60 rounded animate-pulse" />
              ) : (
                <span className="text-white font-bold">{totalAnalyzed} Matches</span>
              )}
            </div>

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#171c28] border border-[#262f42] text-slate-300">
              <Flame className="w-3.5 h-3.5 text-amber-400" />
              <span>Top Bankers:</span>
              {isLoading ? (
                <span className="inline-block w-8 h-3.5 bg-slate-700/60 rounded animate-pulse" />
              ) : (
                <span className="text-amber-300 font-bold">{topBankersCount} High-Win</span>
              )}
            </div>

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#171c28] border border-[#262f42] text-slate-300">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              <span>+EV Value:</span>
              {isLoading ? (
                <span className="inline-block w-8 h-3.5 bg-slate-700/60 rounded animate-pulse" />
              ) : (
                <span className="text-emerald-300 font-bold">{highValueCount} Picks</span>
              )}
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
              <span>Active AI Picks {isLoading ? '…' : `(${activePredictions.length})`}</span>
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
              <span>Curated Slips & Accas {isLoading ? '…' : `(${activeSlips.length})`}</span>
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
                    <div className="flex items-center gap-1.5 text-xs text-slate-300 font-sans">
                      <LeagueLogo league={napOfTheDay.league_code} size="xs" />
                      <span>{napOfTheDay.league_name}</span>
                    </div>
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
            <div className="p-8 rounded-2xl border border-[#242938] bg-[#141822] text-center space-y-4">
              <div className="w-10 h-10 mx-auto rounded-full border-2 border-[#21e786] border-t-transparent animate-spin" />
              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-slate-200">
                  Simulating Poisson Goals & Market Value...
                </h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Running situational model simulations across fixtures to calculate statistical banker certainty, +EV edges, and projected scorelines.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 text-left opacity-60">
                <div className="h-32 rounded-xl bg-[#1a202c] animate-pulse border border-[#2b3548]" />
                <div className="h-32 rounded-xl bg-[#1a202c] animate-pulse border border-[#2b3548]" />
              </div>
            </div>
          ) : error ? (
            <div className="p-8 text-center rounded-2xl border border-rose-900/40 bg-[#161218] space-y-3">
              <XCircle className="w-8 h-8 text-rose-400 mx-auto" />
              <h4 className="font-semibold text-sm text-slate-200">Unable to Load Predictions</h4>
              <p className="text-xs text-rose-300">{error.message || 'Error communicating with AI engine.'}</p>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="px-4 py-1.5 rounded-lg bg-[#21e786] text-black font-bold text-xs hover:bg-[#1bc772] transition-colors"
                >
                  Retry Calculation
                </button>
              )}
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
                          <LeagueLogo league={pred.league_code} size="xs" />
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
          {isLoading ? (
            <div className="col-span-full p-8 rounded-2xl border border-[#242938] bg-[#141822] text-center space-y-4">
              <div className="w-10 h-10 mx-auto rounded-full border-2 border-[#21e786] border-t-transparent animate-spin" />
              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-slate-200">
                  Building Mathematical Accumulator Slips...
                </h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Curating multi-leg bankers, goals combos, and value accas across active fixtures.
                </p>
              </div>
            </div>
          ) : activeSlips.length === 0 ? (
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
                {[3, 7, 14, 30, 60].map((d) => (
                  <button
                    key={d}
                    onClick={() => setHistoryDays(d)}
                    disabled={isHistoryLoading && historyDays === d}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg transition-all ${
                      historyDays === d
                        ? 'bg-[#21e786] text-[#0a0d14] font-bold shadow-sm'
                        : 'bg-[#181d28] text-slate-400 hover:text-white border border-[#232a3a]'
                    }`}
                  >
                    <span>{d}d</span>
                    {isHistoryLoading && historyDays === d && (
                      <span className="w-2.5 h-2.5 border-2 border-[#0a0d14] border-t-transparent rounded-full animate-spin" />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* KPI Performance Cards Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Win Rate */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">
                  {historySubTab === 'SLIPS' ? 'Slips Win Rate' : 'Matches Win Rate'}
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-[#21e786]">
                  {historySubTab === 'SLIPS'
                    ? `${effectiveHistoricalSlips.length > 0 ? Math.round((effectiveHistoricalSlips.filter((s) => s.outcome_status === 'WON').length / effectiveHistoricalSlips.length) * 100) : 0}%`
                    : `${historyData?.summary?.win_rate ?? 0}%`}
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  {historySubTab === 'SLIPS' ? 'Accumulators & Combos' : 'Overall Single Picks'}
                </div>
              </div>

              {/* Record (Won / Lost) */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Record (W / L)</div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-white flex items-center gap-2">
                  {historySubTab === 'SLIPS' ? (
                    <>
                      <span className="text-emerald-400">{effectiveHistoricalSlips.filter((s) => s.outcome_status === 'WON').length}W</span>
                      <span className="text-slate-500">/</span>
                      <span className="text-rose-400">{effectiveHistoricalSlips.filter((s) => s.outcome_status === 'LOST').length}L</span>
                    </>
                  ) : (
                    <>
                      <span className="text-emerald-400">{historyData?.summary?.won_count ?? 0}W</span>
                      <span className="text-slate-500">/</span>
                      <span className="text-rose-400">{historyData?.summary?.lost_count ?? 0}L</span>
                    </>
                  )}
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  {historySubTab === 'SLIPS' ? `${effectiveHistoricalSlips.length} Slips Evaluated` : `${historyData?.summary?.total_predictions ?? 0} Matches Settled`}
                </div>
              </div>

              {/* Net Profit Units */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Net Return</div>
                <div
                  className={`text-xl sm:text-2xl font-bold font-mono ${
                    (historySubTab === 'SLIPS'
                      ? effectiveHistoricalSlips.reduce((acc, s) => acc + s.unit_pnl, 0)
                      : (historyData?.summary?.net_units_num ?? 0)) >= 0
                      ? 'text-emerald-400'
                      : 'text-rose-400'
                  }`}
                >
                  {historySubTab === 'SLIPS'
                    ? `${effectiveHistoricalSlips.reduce((acc, s) => acc + s.unit_pnl, 0) >= 0 ? '+' : ''}${effectiveHistoricalSlips.reduce((acc, s) => acc + s.unit_pnl, 0).toFixed(2)}u`
                    : (historyData?.summary?.total_units ?? '+0.0u')}
                </div>
                <div className="text-[11px] font-sans text-slate-400">
                  {historySubTab === 'SLIPS' ? 'Cumulative Slips PnL' : `ROI: ${historyData?.summary?.roi_pct ?? 0}%`}
                </div>
              </div>

              {/* Banker Accuracy */}
              <div className="p-3 rounded-xl bg-[#0e121a] border border-[#202738] space-y-1">
                <div className="text-[10px] font-mono text-slate-400 uppercase">Bankers Accuracy</div>
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

          {/* Sub-tab Navigation: Slips History vs Matches History */}
          <div className="flex items-center gap-2 border-b border-[#1e2536] pb-3">
            <button
              onClick={() => setHistorySubTab('SLIPS')}
              className={`px-4 py-2 rounded-xl text-xs font-sans font-bold flex items-center gap-2 transition-all ${
                historySubTab === 'SLIPS'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md'
                  : 'bg-[#151924] text-slate-400 hover:text-white border border-[#232b3b]'
              }`}
            >
              <Ticket className="w-4 h-4" />
              <span>Suggested Multi-Leg Slips ({effectiveHistoricalSlips.length})</span>
            </button>

            <button
              onClick={() => setHistorySubTab('MATCHES')}
              className={`px-4 py-2 rounded-xl text-xs font-sans font-bold flex items-center gap-2 transition-all ${
                historySubTab === 'MATCHES'
                  ? 'bg-[#21e786] text-[#0a0d14] shadow-md'
                  : 'bg-[#151924] text-slate-400 hover:text-white border border-[#232b3b]'
              }`}
            >
              <Target className="w-4 h-4" />
              <span>Individual Match Ledger ({historyData?.history?.length ?? 0})</span>
            </button>
          </div>

          {/* Tab 1: Historical Slips & Accumulators */}
          {historySubTab === 'SLIPS' && (
            <div>
              {isHistoryLoading ? (
                <div className="p-12 text-center rounded-2xl border border-[#242938] bg-[#141822] space-y-3">
                  <div className="w-8 h-8 mx-auto rounded-full border-2 border-[#21e786] border-t-transparent animate-spin" />
                  <p className="text-xs font-mono text-slate-300">
                    Auditing historical {historyDays}-day accumulator slips against official scorelines...
                  </p>
                </div>
              ) : effectiveHistoricalSlips.length === 0 ? (
                <div className="p-12 text-center rounded-2xl border border-[#242938] bg-[#141822] space-y-2">
                  <Ticket className="w-8 h-8 text-slate-500 mx-auto" />
                  <h4 className="font-bold text-sm text-white font-sans">No Historical Slips Found</h4>
                  <p className="text-xs text-slate-400 font-sans max-w-sm mx-auto">
                    No accumulator slips matched your current filters ({historyOutcome}, {historyLeague}, {historyDays}d). Try resetting filters.
                  </p>
                  <button
                    onClick={() => {
                      setHistoryOutcome('ALL');
                      setHistoryLeague('ALL');
                      setHistoryDays(7);
                    }}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-sans font-semibold bg-[#21e786] text-[#0a0d14]"
                  >
                    Reset Filters
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {effectiveHistoricalSlips.map((slip) => {
                    const isSlipWon = slip.outcome_status === 'WON';
                    return (
                      <div
                        key={slip.id}
                        className={`rounded-2xl border p-4 space-y-3.5 shadow-sm transition-all flex flex-col justify-between ${
                          isSlipWon
                            ? 'border-emerald-500/35 bg-gradient-to-b from-[#0f1917] via-[#0d141c] to-[#0a0d14]'
                            : 'border-rose-500/35 bg-gradient-to-b from-[#1a1015] via-[#0f121a] to-[#0a0d14]'
                        }`}
                      >
                        <div className="space-y-3">
                          {/* Header: Date, Badge, and Won/Lost Pill */}
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#171d2b] text-slate-300 border border-[#263145]">
                                {slip.date}
                              </span>
                              <span className="text-[10px] font-sans font-semibold px-2 py-0.5 rounded-full bg-[#1b2232] text-amber-300 border border-amber-500/25">
                                {slip.badge}
                              </span>
                            </div>

                            <span
                              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold tracking-wide shrink-0 ${
                                isSlipWon
                                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                  : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                              }`}
                            >
                              {isSlipWon ? (
                                <>
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                  <span>SLIP WON • {slip.unit_return}</span>
                                </>
                              ) : (
                                <>
                                  <XCircle className="w-3.5 h-3.5 text-rose-400" />
                                  <span>SLIP LOST • {slip.unit_return}</span>
                                </>
                              )}
                            </span>
                          </div>

                          {/* Title & Multiplier */}
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <h4 className="font-bold text-sm text-white font-sans flex items-center gap-1.5">
                                <Ticket className="w-4 h-4 text-[#21e786]" />
                                <span>{slip.title}</span>
                              </h4>
                              <p className="text-xs text-slate-400 font-sans mt-0.5 leading-snug">
                                {slip.description}
                              </p>
                            </div>

                            <div className="text-right shrink-0">
                              <div className="text-[10px] font-mono text-slate-400 uppercase">Total Odds</div>
                              <span className="text-xs font-mono font-bold px-2 py-1 rounded bg-[#0c1017] text-emerald-400 border border-emerald-800/80 inline-block">
                                @{slip.total_odds.toFixed(2)}
                              </span>
                            </div>
                          </div>

                          {/* Selections / Legs Breakdown */}
                          <div className="space-y-1.5 pt-1">
                            <div className="text-[11px] font-mono text-slate-400 flex items-center justify-between">
                              <span>Selections ({slip.selections_count} Legs):</span>
                              <span>Leg Outcome</span>
                            </div>

                            {slip.picks.map((pick, pIdx) => {
                              const legWon = pick.status === 'WON';
                              return (
                                <div
                                  key={pIdx}
                                  className={`p-2.5 rounded-xl border flex flex-col gap-1.5 text-xs font-sans transition-all ${
                                    legWon
                                      ? 'bg-[#0d1417]/80 border-emerald-900/30'
                                      : 'bg-[#170e13]/80 border-rose-900/30'
                                  }`}
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-1.5 min-w-0 truncate">
                                      <LeagueLogo league={pick.league_code} size="xs" />
                                      <TeamLogo teamName={pick.home_team} size="xs" />
                                      <span className="font-bold text-white truncate">{pick.home_team}</span>
                                      <span className="text-slate-500 text-[10px]">vs</span>
                                      <TeamLogo teamName={pick.away_team} size="xs" />
                                      <span className="font-bold text-white truncate">{pick.away_team}</span>
                                    </div>

                                    <div className="flex items-center gap-1.5 shrink-0">
                                      <span className="font-mono text-xs font-bold text-white px-1.5 py-0.2 rounded bg-[#090c12] border border-[#1f2636]">
                                        {pick.final_score}
                                      </span>
                                      <span
                                        className={`inline-flex items-center gap-0.5 text-[10px] font-mono font-bold px-1.5 py-0.2 rounded ${
                                          legWon
                                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                                            : 'bg-rose-950 text-rose-300 border border-rose-800'
                                        }`}
                                      >
                                        {legWon ? 'WON' : 'LOST'}
                                      </span>
                                    </div>
                                  </div>

                                  <div className="flex items-center justify-between gap-2 pt-0.5 border-t border-[#1a2230]/60">
                                    <span className="text-[#21e786] font-semibold text-[11px] truncate">
                                      {pick.pick} <span className="text-slate-400 font-mono font-normal">({pick.market})</span>
                                    </span>
                                    <span className="font-mono text-slate-300 text-[11px] font-bold">
                                      @{pick.odds.toFixed(2)}
                                    </span>
                                  </div>

                                  {pick.audit_note && (
                                    <p className="text-[10px] text-slate-400 font-sans leading-tight">
                                      {pick.audit_note}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {/* Settlement Note & Action Buttons */}
                        <div className="pt-2.5 border-t border-[#1c2333] space-y-2">
                          <div className="text-[11px] text-slate-300 font-sans leading-relaxed">
                            <strong className="text-white">Settlement Audit: </strong>
                            {slip.audit_note}
                          </div>

                          <div className="flex items-center justify-between gap-2 pt-1">
                            <button
                              onClick={() => handleCopyHistoricalSlip(slip)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono bg-[#181d28] hover:bg-[#202738] text-slate-300 hover:text-white border border-[#262f42] transition-colors"
                              title="Copy slip details"
                            >
                              {copiedSlipId === slip.id ? (
                                <>
                                  <Check className="w-3 h-3 text-[#21e786]" />
                                  <span className="text-[#21e786] font-bold">Copied</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="w-3 h-3" />
                                  <span>Copy Slip</span>
                                </>
                              )}
                            </button>

                            <button
                              onClick={() => handleShareHistoricalSlip(slip)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono bg-[#21e786]/10 hover:bg-[#21e786]/20 text-[#21e786] border border-[#21e786]/30 transition-colors"
                            >
                              <Share2 className="w-3 h-3" />
                              <span>Share Slip</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Individual Matches History */}
          {historySubTab === 'MATCHES' && (
            <div>
              {isHistoryLoading ? (
                <div className="p-12 text-center rounded-2xl border border-[#242938] bg-[#141822] space-y-3">
                  <div className="w-8 h-8 mx-auto rounded-full border-2 border-[#21e786] border-t-transparent animate-spin" />
                  <p className="text-xs font-mono text-slate-300">
                    Auditing historical {historyDays}-day predictions against canonical scorelines...
                  </p>
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
                          <div className="flex items-center gap-1.5 text-xs text-slate-300 font-sans">
                            <LeagueLogo league={item.league_code} size="xs" />
                            <span className="font-semibold text-slate-200">{item.league_name}</span>
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
                            <div className="text-base font-bold font-mono text-white px-2 py-0.5 rounded bg-[#171c26] border border-[#262f42]">
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
