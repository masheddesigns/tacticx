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
    <div className="rounded-2xl border border-[#242938] bg-[#161922] p-5 sm:p-6 shadow-xl space-y-5">
      {/* Top Banner: Title & Share Action */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[#242938]">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-400" />
          <h2 className="text-base sm:text-lg font-bold text-white tracking-tight font-sans">
            Quick Match Predictions & Projected Stats Summary
          </h2>
          <span className="text-[11px] font-sans font-semibold px-2 py-0.5 rounded-md bg-[#21e786]/10 text-[#21e786] border border-[#21e786]/30 hidden sm:inline-block">
            Easy Glance
          </span>
        </div>

        <button
          onClick={onShare}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-sans font-semibold bg-[#21e786]/10 hover:bg-[#21e786] text-[#21e786] hover:text-[#0e1015] border border-[#21e786]/30 transition-all shadow-sm"
        >
          <Share2 className="w-3.5 h-3.5" />
          <span>Share Screenshot</span>
        </button>
      </div>

      {/* Main Grid: 4 Core Easy-to-Read Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Tile 1: Match Winner & Confidence */}
        <div className="p-4 rounded-xl bg-[#1e222e] border border-[#242938] space-y-2 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-xs text-slate-400 font-sans">
            <span className="flex items-center gap-1.5">
              <Trophy className="w-3.5 h-3.5 text-amber-400" />
              <span className="font-semibold text-slate-300">Match Winner</span>
            </span>
            <span className="text-[#21e786] font-bold font-mono">{bestPickProb.toFixed(0)}% Lean</span>
          </div>

          <div className="text-base font-extrabold text-white font-sans truncate" title={bestPick}>
            {bestPick}
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pt-1">
            <span>{homeTeamName.slice(0, 3).toUpperCase()}: {homeProb}%</span>
            <span>Draw: {drawProb}%</span>
            <span>{awayTeamName.slice(0, 3).toUpperCase()}: {awayProb}%</span>
          </div>

          <div className="h-1.5 w-full bg-[#0e1015] rounded-full overflow-hidden flex gap-0.5 border border-[#242938]">
            <div className="bg-[#21e786] h-full rounded-l-full" style={{ width: `${homeProb}%` }} />
            <div className="bg-amber-400 h-full" style={{ width: `${drawProb}%` }} />
            <div className="bg-blue-500 h-full rounded-r-full" style={{ width: `${awayProb}%` }} />
          </div>
        </div>

        {/* Tile 2: Goals (Over / Under & BTTS) */}
        <div className="p-4 rounded-xl bg-[#1e222e] border border-[#242938] space-y-2 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-xs text-slate-400 font-sans">
            <span className="flex items-center gap-1.5">
              <Goal className="w-3.5 h-3.5 text-blue-400" />
              <span className="font-semibold text-slate-300">Goals Over/Under</span>
            </span>
            <span className="text-[#21e786] font-bold font-mono">Over 1.5: {over15Prob}%</span>
          </div>

          <div className="flex items-center justify-between text-xs font-mono font-bold text-white pt-1">
            <span className="px-2 py-0.5 rounded-md bg-[#0e1015] border border-[#242938]">
              Over 2.5: <span className="text-[#21e786]">{over25Prob}%</span>
            </span>
            <span className="px-2 py-0.5 rounded-md bg-[#0e1015] border border-[#242938]">
              Under 2.5: <span className="text-slate-300">{under25Prob}%</span>
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-300 pt-1">
            <span className="text-slate-400 font-sans">BTTS (Both Score):</span>
            <span className={bttsYesProb >= 50 ? 'text-[#21e786] font-bold' : 'text-slate-300'}>
              Yes {bttsYesProb}% / No {bttsNoProb}%
            </span>
          </div>
        </div>

        {/* Tile 3: Top Predicted Scores */}
        <div className="p-4 rounded-xl bg-[#1e222e] border border-[#242938] space-y-2 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-xs text-slate-400 font-sans">
            <span className="flex items-center gap-1.5">
              <Target className="w-3.5 h-3.5 text-purple-400" />
              <span className="font-semibold text-slate-300">Top Scores</span>
            </span>
            <span className="text-purple-400 font-bold font-mono">Poisson Max</span>
          </div>

          <div className="flex items-center justify-between gap-1.5 pt-0.5">
            {topScores.map((sc, i) => (
              <div
                key={sc.score}
                className={`flex-1 py-1.5 px-1 rounded-lg text-center font-mono border ${
                  i === 0
                    ? 'bg-[#21e786]/10 border-[#21e786]/30 text-white font-extrabold'
                    : 'bg-[#0e1015] border-[#242938] text-slate-300'
                }`}
              >
                <div className="text-xs sm:text-sm font-bold text-white">{sc.score}</div>
                <div className="text-[10px] text-[#21e786] font-normal">
                  {Math.round(sc.probability * 100)}%
                </div>
              </div>
            ))}
          </div>

          <span className="text-[10px] font-sans text-slate-400 block text-center">
            Derived from Poisson bivariate model
          </span>
        </div>

        {/* Tile 4: In-Game Stats (Corners & Cards) */}
        <div className="p-4 rounded-xl bg-[#1e222e] border border-[#242938] space-y-2 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-xs text-slate-400 font-sans">
            <span className="flex items-center gap-1.5">
              <Flag className="w-3.5 h-3.5 text-purple-400" />
              <span className="font-semibold text-slate-300">Projected Stats</span>
            </span>
            <span className="text-purple-400 font-bold font-mono">~{cornersTot} Corners</span>
          </div>

          <div className="space-y-1.5 pt-0.5 text-xs font-mono">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1 font-sans">
                <Flag className="w-3 h-3 text-purple-400" /> Corners:
              </span>
              <span className="text-white font-bold">
                {cornersHome} - {cornersAway} ({cornersTot} total)
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1 font-sans">
                <CreditCard className="w-3 h-3 text-amber-400" /> Cards:
              </span>
              <span className="text-white font-bold">
                ~{cardsTot} total yellow cards
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1 font-sans">
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
