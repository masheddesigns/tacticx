import React, { useState } from 'react';
import { Target, Flag, AlertOctagon, HelpCircle, TrendingUp } from 'lucide-react';
import { StatProjectionsResponse } from '../../api/types';
import { formatProbability, formatDecimalOdds, getPayoutExplanation } from '../../lib/utils';

export interface SituationalStatsCardProps {
  projections?: StatProjectionsResponse | null;
  homeTeamName?: string;
  awayTeamName?: string;
  isLoading?: boolean;
}

export const SituationalStatsCard: React.FC<SituationalStatsCardProps> = ({
  projections,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
  isLoading = false,
}) => {
  const [selectedBetStake, setSelectedBetStake] = useState<number>(10);
  const [selectedCategory, setSelectedCategory] = useState<'all' | 'corners' | 'shots' | 'cards'>('all');

  if (isLoading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-center animate-pulse text-xs font-mono text-slate-400">
        Calculating situational props & odds (corners, shots, cards)...
      </div>
    );
  }

  if (!projections) {
    return null;
  }

  const { team_projections, combined_projections, situation_markets } = projections;
  const filteredMarkets = selectedCategory === 'all'
    ? situation_markets
    : situation_markets.filter((m) => m.category === selectedCategory);

  return (
    <section aria-labelledby="situational-stats-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Target className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 id="situational-stats-heading" className="font-semibold text-sm text-slate-100">
                Situational Markets & Expected Match Stats
              </h2>
              <span className="text-[10px] uppercase font-mono font-bold px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                PROPS & DECIMAL ODDS
              </span>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              Expected team corners, shots on target, and card totals with decimal payout multipliers
            </span>
          </div>
        </div>

        {/* Stake Selector */}
        <div className="flex items-center gap-2 text-xs font-mono bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800">
          <span className="text-slate-400">Simulate Bet:</span>
          {[10, 25, 50].map((stake) => (
            <button
              key={stake}
              onClick={() => setSelectedBetStake(stake)}
              className={`px-2 py-0.5 rounded text-xs transition-colors ${
                selectedBetStake === stake
                  ? 'bg-emerald-600 text-white font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              ${stake}
            </button>
          ))}
        </div>
      </div>

      {/* Team-by-Team Expected Performance Grid */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-mono text-slate-300">
          <span className="font-semibold">Team-wise Baseline Averages:</span>
          <span className="text-slate-400 text-[11px]">Expected per 90 min</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Home Team */}
          <div className="p-4 rounded-lg bg-slate-900/60 border border-blue-900/40 space-y-2.5">
            <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
              <span className="font-bold text-xs text-blue-400 font-mono truncate">{homeTeamName} (Home)</span>
              <span className="text-[10px] text-slate-400 font-mono">Projection</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400 flex items-center gap-1">
                  <Flag className="w-3 h-3 text-blue-400" /> Corners:
                </span>
                <span className="text-slate-100 font-bold">{team_projections.home.corners}</span>
              </div>
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400 flex items-center gap-1">
                  <Target className="w-3 h-3 text-blue-400" /> Shots Total:
                </span>
                <span className="text-slate-100 font-bold">{team_projections.home.shots_total}</span>
              </div>
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400">On Target:</span>
                <span className="text-slate-100 font-bold">{team_projections.home.shots_on_target}</span>
              </div>
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400 flex items-center gap-1">
                  <AlertOctagon className="w-3 h-3 text-amber-400" /> Yellows:
                </span>
                <span className="text-amber-300 font-bold">{team_projections.home.yellow_cards}</span>
              </div>
            </div>
          </div>

          {/* Away Team */}
          <div className="p-4 rounded-lg bg-slate-900/60 border border-emerald-900/40 space-y-2.5">
            <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
              <span className="font-bold text-xs text-emerald-400 font-mono truncate">{awayTeamName} (Away)</span>
              <span className="text-[10px] text-slate-400 font-mono">Projection</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400 flex items-center gap-1">
                  <Flag className="w-3 h-3 text-emerald-400" /> Corners:
                </span>
                <span className="text-slate-100 font-bold">{team_projections.away.corners}</span>
              </div>
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400 flex items-center gap-1">
                  <Target className="w-3 h-3 text-emerald-400" /> Shots Total:
                </span>
                <span className="text-slate-100 font-bold">{team_projections.away.shots_total}</span>
              </div>
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400">On Target:</span>
                <span className="text-slate-100 font-bold">{team_projections.away.shots_on_target}</span>
              </div>
              <div className="flex justify-between items-center bg-slate-950 p-2 rounded border border-slate-800/80">
                <span className="text-slate-400 flex items-center gap-1">
                  <AlertOctagon className="w-3 h-3 text-amber-400" /> Yellows:
                </span>
                <span className="text-amber-300 font-bold">{team_projections.away.yellow_cards}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Situational Markets with European Decimal Odds */}
      <div className="space-y-3 pt-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-semibold text-slate-200">
              Situational Odds & Payout Multipliers:
            </span>
            <span className="text-[10px] font-sans text-slate-400">
              (Decimal format e.g. 2.50 = 2.5x total payout)
            </span>
          </div>

          {/* Category Filter */}
          <div className="flex rounded bg-slate-900 border border-slate-800 p-0.5 text-xs font-mono">
            {(['all', 'corners', 'shots', 'cards'] as const).map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-0.5 rounded capitalize transition-colors ${
                  selectedCategory === cat
                    ? 'bg-slate-800 text-emerald-400 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Market Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filteredMarkets.map((m, idx) => (
            <div
              key={idx}
              className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-all flex flex-col justify-between space-y-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="font-semibold text-xs text-slate-100 font-sans block">{m.market_name}</span>
                  <span className="text-[10px] text-slate-400 font-mono block mt-0.5">{m.description}</span>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-base font-mono font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-800/80 px-2 py-0.5 rounded">
                    {m.decimal_odds.toFixed(2)}
                  </div>
                  <span className="text-[9px] font-mono text-slate-400 uppercase">Decimal Odds</span>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-slate-400">Probability:</span>
                  <span className="font-bold text-slate-200">{formatProbability(m.probability)}</span>
                </div>
                <span className="text-[11px] text-emerald-400/90 font-medium font-sans">
                  {getPayoutExplanation(m.decimal_odds, selectedBetStake)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Explanatory Guide Box for Normal Users */}
      <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800/80 text-[11px] text-slate-400 font-sans space-y-1">
        <div className="flex items-center gap-1.5 font-semibold text-slate-300 font-mono text-xs">
          <HelpCircle className="w-3.5 h-3.5 text-emerald-400" />
          <span>How European Decimal Odds Work:</span>
        </div>
        <p className="leading-relaxed">
          Decimal odds represent the total payout for every $1 you bet (including your original stake).
          For example, odds of <strong className="text-slate-200 font-mono">2.50</strong> mean a <strong className="text-slate-200 font-mono">$10</strong> bet returns <strong className="text-emerald-400 font-mono">$25.00</strong> ($15 profit + your $10 stake). Higher odds indicate larger potential return with lower statistical likelihood.
        </p>
      </div>
    </section>
  );
};
