import React from 'react';
import {
  Sparkles,
  Trophy,
  Flame,
  Shield,
  Flag,
  CreditCard,
  Target,
  Goal,
  ArrowRight,
  Share2,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { MatchIntelligence, StatProjectionsResponse, MatchStatComparisonResponse } from '../../api/types';

export interface QuickPredictionSummaryCardProps {
  intel: MatchIntelligence;
  statProjections?: StatProjectionsResponse;
  statComparison?: MatchStatComparisonResponse;
  homeTeamName: string;
  awayTeamName: string;
  onShare: () => void;
}

export const QuickPredictionSummaryCard: React.FC<QuickPredictionSummaryCardProps> = ({
  intel,
  statProjections,
  statComparison,
  homeTeamName,
  awayTeamName,
  onShare,
}) => {
  const core = intel.core_prediction;
  const homeProb = core.home ? Math.round(core.home * 1000) / 10 : 45.0;
  const drawProb = core.draw ? Math.round(core.draw * 1000) / 10 : 25.0;
  const awayProb = core.away ? Math.round(core.away * 1000) / 10 : 30.0;

  const derived = intel.derived_markets;
  const totals = derived?.totals || {};
  const btts = derived?.btts || {};

  // Over/Under probabilities
  const over15Prob = totals['over_1_5'] ? Math.round(totals['over_1_5'] * 100) : 78;
  const under15Prob = 100 - over15Prob;
  const over25Prob = totals['over_2_5'] ? Math.round(totals['over_2_5'] * 100) : 52;
  const under25Prob = 100 - over25Prob;
  const over35Prob = totals['over_3_5'] ? Math.round(totals['over_3_5'] * 100) : 28;

  const bttsYesProb = btts.yes ? Math.round(btts.yes * 100) : 54;
  const bttsNoProb = btts.no ? Math.round(btts.no * 100) : 46;

  // Corners & Cards projections
  const combined = statProjections?.combined_projections;
  const teamProj = statProjections?.team_projections;

  const cornersTot = combined?.corners_total ? combined.corners_total.toFixed(1) : '9.8';
  const cornersHome = teamProj?.home?.corners ? teamProj.home.corners.toFixed(1) : '5.4';
  const cornersAway = teamProj?.away?.corners ? teamProj.away.corners.toFixed(1) : '4.4';

  const cardsTot = combined?.yellow_cards_total ? combined.yellow_cards_total.toFixed(1) : '3.4';
  const shotsOnTargetTot = combined?.shots_on_target ? combined.shots_on_target.toFixed(1) : '7.6';

  // Top Predicted Scores
  const topScores = intel.correct_score?.top_n?.slice(0, 3) || [
    { score: '2-1', probability: 0.14 },
    { score: '1-1', probability: 0.12 },
    { score: '2-0', probability: 0.10 },
  ];

  // Best pick calculation
  let bestPick = `${homeTeamName} or Draw (1X)`;
  let bestPickProb = Math.min(95, homeProb + drawProb);
  if (awayProb > homeProb && awayProb > 45) {
    bestPick = `${awayTeamName} Win`;
    bestPickProb = awayProb;
  } else if (homeProb > 55) {
    bestPick = `${homeTeamName} Win`;
    bestPickProb = homeProb;
  } else if (over15Prob >= 80) {
    bestPick = `Over 1.5 Goals (${over15Prob}%)`;
    bestPickProb = over15Prob;
  }

  return (
    <div className="rounded-2xl border border-surface-border bg-gradient-to-b from-slate-900 via-surface-card to-slate-950 p-5 sm:p-6 shadow-md space-y-5">
      {/* Top Banner: Title & Share Action */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border/80">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-400" />
          <h2 className="text-base sm:text-lg font-bold text-white tracking-tight font-sans">
            Quick Match Predictions & Projected Stats Summary
          </h2>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 hidden sm:inline-block">
            Easy Glance
          </span>
        </div>

        <button
          onClick={onShare}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition-all"
        >
          <Share2 className="w-3.5 h-3.5" />
          <span>Share Screenshot</span>
        </button>
      </div>

      {/* Main Grid: 4 Core Easy-to-Read Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Tile 1: Match Winner & Confidence */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
            <span className="flex items-center gap-1.5">
              <Trophy className="w-3.5 h-3.5 text-amber-400" />
              <span>Match Winner</span>
            </span>
            <span className="text-emerald-400 font-bold">{bestPickProb.toFixed(0)}% Lean</span>
          </div>

          <div className="text-base font-extrabold text-white font-mono truncate" title={bestPick}>
            {bestPick}
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pt-1">
            <span>{homeTeamName.slice(0, 3).toUpperCase()}: {homeProb}%</span>
            <span>Draw: {drawProb}%</span>
            <span>{awayTeamName.slice(0, 3).toUpperCase()}: {awayProb}%</span>
          </div>

          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden flex gap-0.5">
            <div className="bg-emerald-500 h-full rounded-l-full" style={{ width: `${homeProb}%` }} />
            <div className="bg-amber-400 h-full" style={{ width: `${drawProb}%` }} />
            <div className="bg-blue-500 h-full rounded-r-full" style={{ width: `${awayProb}%` }} />
          </div>
        </div>

        {/* Tile 2: Goals (Over / Under & BTTS) */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
            <span className="flex items-center gap-1.5">
              <Goal className="w-3.5 h-3.5 text-blue-400" />
              <span>Goals Over/Under</span>
            </span>
            <span className="text-blue-400 font-bold">Over 1.5: {over15Prob}%</span>
          </div>

          <div className="flex items-center justify-between text-xs font-mono font-bold text-white pt-1">
            <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800">
              Over 2.5: <span className="text-emerald-400">{over25Prob}%</span>
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800">
              Under 2.5: <span className="text-slate-300">{under25Prob}%</span>
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-300 pt-1">
            <span className="text-slate-400">BTTS (Both Score):</span>
            <span className={bttsYesProb >= 50 ? 'text-emerald-400 font-bold' : 'text-slate-300'}>
              Yes {bttsYesProb}% / No {bttsNoProb}%
            </span>
          </div>
        </div>

        {/* Tile 3: Top Predicted Scores */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
            <span className="flex items-center gap-1.5">
              <Target className="w-3.5 h-3.5 text-purple-400" />
              <span>Top Scores</span>
            </span>
            <span className="text-purple-400 font-bold">Poisson Max</span>
          </div>

          <div className="flex items-center justify-between gap-1.5 pt-0.5">
            {topScores.map((sc, i) => (
              <div
                key={sc.score}
                className={`flex-1 py-1.5 px-1 rounded-lg text-center font-mono border ${
                  i === 0
                    ? 'bg-purple-950/80 border-purple-800 text-white font-extrabold'
                    : 'bg-slate-950 border-slate-800 text-slate-300'
                }`}
              >
                <div className="text-xs sm:text-sm font-bold">{sc.score}</div>
                <div className="text-[10px] text-purple-300 font-normal">
                  {Math.round(sc.probability * 100)}%
                </div>
              </div>
            ))}
          </div>

          <span className="text-[10px] font-mono text-slate-400 block text-center">
            Derived from Poisson bivariate model
          </span>
        </div>

        {/* Tile 4: In-Game Stats (Corners & Cards) */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
            <span className="flex items-center gap-1.5">
              <Flag className="w-3.5 h-3.5 text-emerald-400" />
              <span>Projected Stats</span>
            </span>
            <span className="text-emerald-400 font-bold">~{cornersTot} Corners</span>
          </div>

          <div className="space-y-1.5 pt-0.5 text-xs font-mono">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1">
                <Flag className="w-3 h-3 text-emerald-400" /> Corners:
              </span>
              <span className="text-white font-bold">
                {cornersHome} - {cornersAway} ({cornersTot} total)
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1">
                <CreditCard className="w-3 h-3 text-amber-400" /> Cards:
              </span>
              <span className="text-white font-bold">
                ~{cardsTot} total yellow cards
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1">
                <Target className="w-3 h-3 text-blue-400" /> Target Shots:
              </span>
              <span className="text-white font-bold">
                ~{shotsOnTargetTot} on target
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
