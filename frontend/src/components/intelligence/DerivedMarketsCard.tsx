import React, { useState } from 'react';
import { Layers, ShieldCheck } from 'lucide-react';
import { DerivedMarketsSection } from '../../api/types';
import { formatProbability, formatDecimalOdds } from '../../lib/utils';

export interface DerivedMarketsCardProps {
  markets: DerivedMarketsSection;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const DerivedMarketsCard: React.FC<DerivedMarketsCardProps> = ({
  markets,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const [activeTab, setActiveTab] = useState<'double_chance' | 'totals' | 'btts' | 'team_totals'>('double_chance');

  const dc = markets.double_chance || {};
  const totals = markets.totals || {};
  const btts = markets.btts || {};
  const teamTotals = markets.team_totals || {};

  return (
    <section aria-labelledby="derived-markets-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-purple-500/10 border border-purple-500/20 text-purple-400">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h2 id="derived-markets-heading" className="font-semibold text-sm text-slate-100">Derived Outcome Probabilities</h2>
            <span className="text-[11px] font-mono text-slate-400">Analytical projections directly from backend engine</span>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex rounded-lg bg-slate-900 p-1 border border-slate-800 text-xs font-mono">
          <button
            onClick={() => setActiveTab('double_chance')}
            className={`px-3 py-1 rounded transition-colors ${
              activeTab === 'double_chance' ? 'bg-slate-800 text-emerald-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Double Chance
          </button>
          <button
            onClick={() => setActiveTab('totals')}
            className={`px-3 py-1 rounded transition-colors ${
              activeTab === 'totals' ? 'bg-slate-800 text-emerald-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Totals
          </button>
          <button
            onClick={() => setActiveTab('btts')}
            className={`px-3 py-1 rounded transition-colors ${
              activeTab === 'btts' ? 'bg-slate-800 text-emerald-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            BTTS
          </button>
          <button
            onClick={() => setActiveTab('team_totals')}
            className={`px-3 py-1 rounded transition-colors ${
              activeTab === 'team_totals' ? 'bg-slate-800 text-emerald-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Team Totals
          </button>
        </div>
      </div>

      {/* Tab 1: Double Chance */}
      {activeTab === 'double_chance' && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center flex flex-col justify-between">
            <div>
              <span className="text-xs font-mono font-semibold text-slate-300 block">1X (Home Win or Draw)</span>
              <div className="text-xl font-mono font-bold text-slate-100 mt-1">
                {formatProbability(dc['1x'])}
              </div>
              <div className="mt-1 flex items-center justify-center gap-1.5">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-emerald-400 border border-slate-700">
                  {formatDecimalOdds(dc['1x'], true)}
                </span>
                <span className="text-[10px] font-mono text-slate-400">Odds</span>
              </div>
            </div>
            <span className="text-[10px] text-slate-500 font-sans mt-2 block">
              Bet x {formatDecimalOdds(dc['1x'], true)} payout
            </span>
          </div>

          <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center flex flex-col justify-between">
            <div>
              <span className="text-xs font-mono font-semibold text-slate-300 block">X2 (Draw or Away Win)</span>
              <div className="text-xl font-mono font-bold text-slate-100 mt-1">
                {formatProbability(dc['x2'])}
              </div>
              <div className="mt-1 flex items-center justify-center gap-1.5">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-emerald-400 border border-slate-700">
                  {formatDecimalOdds(dc['x2'], true)}
                </span>
                <span className="text-[10px] font-mono text-slate-400">Odds</span>
              </div>
            </div>
            <span className="text-[10px] text-slate-500 font-sans mt-2 block">
              Bet x {formatDecimalOdds(dc['x2'], true)} payout
            </span>
          </div>

          <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center flex flex-col justify-between">
            <div>
              <span className="text-xs font-mono font-semibold text-slate-300 block">12 (Any Team Wins)</span>
              <div className="text-xl font-mono font-bold text-slate-100 mt-1">
                {formatProbability(dc['12'])}
              </div>
              <div className="mt-1 flex items-center justify-center gap-1.5">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-emerald-400 border border-slate-700">
                  {formatDecimalOdds(dc['12'], true)}
                </span>
                <span className="text-[10px] font-mono text-slate-400">Odds</span>
              </div>
            </div>
            <span className="text-[10px] text-slate-500 font-sans mt-2 block">
              Bet x {formatDecimalOdds(dc['12'], true)} payout
            </span>
          </div>
        </div>
      )}

      {/* Tab 2: Over / Under Totals */}
      {activeTab === 'totals' && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {['0_5', '1_5', '2_5', '3_5'].map((thresh) => {
            const overKey = `over_${thresh}`;
            const underKey = `under_${thresh}`;
            const displayLabel = thresh.replace('_', '.');
            const overVal = totals[overKey];
            const underVal = totals[underKey];

            return (
              <div key={thresh} className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2">
                <span className="text-[11px] font-mono font-semibold text-purple-300 block text-center pb-1 border-b border-slate-800">
                  Total {displayLabel} Goals
                </span>
                <div className="space-y-1">
                  <div className="flex justify-between items-center text-xs font-mono">
                    <span className="text-slate-400">Over:</span>
                    <div className="flex items-center gap-1">
                      <span className="text-slate-100 font-bold">{formatProbability(overVal)}</span>
                      <span className="text-[10px] text-emerald-400 font-mono bg-slate-950 px-1 py-0.2 rounded border border-slate-800">
                        {formatDecimalOdds(overVal, true)}
                      </span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-xs font-mono">
                    <span className="text-slate-400">Under:</span>
                    <div className="flex items-center gap-1">
                      <span className="text-slate-300">{formatProbability(underVal)}</span>
                      <span className="text-[10px] text-emerald-400 font-mono bg-slate-950 px-1 py-0.2 rounded border border-slate-800">
                        {formatDecimalOdds(underVal, true)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Tab 3: BTTS */}
      {activeTab === 'btts' && (
        <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
          <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-center">
            <span className="text-xs font-mono font-semibold text-slate-300 block">Both Teams To Score: YES</span>
            <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
              {formatProbability(btts.yes)}
            </div>
            <div className="mt-1 flex items-center justify-center gap-1.5">
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                {formatDecimalOdds(btts.yes, true)}
              </span>
              <span className="text-[10px] font-mono text-slate-400">Odds</span>
            </div>
            <span className="text-[10px] text-slate-500 font-sans mt-2 block">
              Bet x {formatDecimalOdds(btts.yes, true)} payout
            </span>
          </div>

          <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-center">
            <span className="text-xs font-mono font-semibold text-slate-300 block">Both Teams To Score: NO</span>
            <div className="text-2xl font-mono font-bold text-slate-200 mt-1">
              {formatProbability(btts.no)}
            </div>
            <div className="mt-1 flex items-center justify-center gap-1.5">
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
                {formatDecimalOdds(btts.no, true)}
              </span>
              <span className="text-[10px] font-mono text-slate-400">Odds</span>
            </div>
            <span className="text-[10px] text-slate-500 font-sans mt-2 block">
              Bet x {formatDecimalOdds(btts.no, true)} payout
            </span>
          </div>
        </div>
      )}

      {/* Tab 4: Team Totals */}
      {activeTab === 'team_totals' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2">
            <span className="text-xs font-mono font-semibold text-blue-400 block truncate" title={homeTeamName}>
              {homeTeamName} Individual Totals
            </span>
            <div className="space-y-1 text-xs font-mono">
              <div className="flex justify-between py-0.5 border-b border-slate-800/80">
                <span className="text-slate-400">Over 0.5:</span>
                <span className="text-slate-200 font-bold">{formatProbability(teamTotals.home?.over_0_5)}</span>
              </div>
              <div className="flex justify-between py-0.5 border-b border-slate-800/80">
                <span className="text-slate-400">Over 1.5:</span>
                <span className="text-slate-200">{formatProbability(teamTotals.home?.over_1_5)}</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-slate-400">Over 2.5:</span>
                <span className="text-slate-200">{formatProbability(teamTotals.home?.over_2_5)}</span>
              </div>
            </div>
          </div>

          <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2">
            <span className="text-xs font-mono font-semibold text-emerald-400 block truncate" title={awayTeamName}>
              {awayTeamName} Individual Totals
            </span>
            <div className="space-y-1 text-xs font-mono">
              <div className="flex justify-between py-0.5 border-b border-slate-800/80">
                <span className="text-slate-400">Over 0.5:</span>
                <span className="text-slate-200 font-bold">{formatProbability(teamTotals.away?.over_0_5)}</span>
              </div>
              <div className="flex justify-between py-0.5 border-b border-slate-800/80">
                <span className="text-slate-400">Over 1.5:</span>
                <span className="text-slate-200">{formatProbability(teamTotals.away?.over_1_5)}</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-slate-400">Over 2.5:</span>
                <span className="text-slate-200">{formatProbability(teamTotals.away?.over_2_5)}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-slate-400">
        <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
        <span>Values are projected strictly from bivariate Poisson model convolution. No client-side recalculation.</span>
      </div>
    </section>
  );
};
