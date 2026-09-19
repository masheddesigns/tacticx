import React, { useState } from 'react';
import { Sliders, RefreshCw, Hash, ArrowRight } from 'lucide-react';
import { ScenarioItem } from '../../api/types';
import { formatProbability, formatLambda } from '../../lib/utils';
import { ProbabilityBar } from './ProbabilityBar';
import { Badge } from '../common/Badge';

export interface ScenarioAnalysisCardProps {
  scenarios: ScenarioItem[];
  homeTeamName?: string;
  awayTeamName?: string;
}

export const ScenarioAnalysisCard: React.FC<ScenarioAnalysisCardProps> = ({
  scenarios,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

  if (!scenarios || scenarios.length === 0) {
    return null;
  }

  const baseline = scenarios[0];
  const current = scenarios[selectedIdx] || baseline;
  const isBaseline = selectedIdx === 0;

  const diff = current.difference_from_baseline?.probabilities;

  return (
    <section aria-labelledby="scenario-analysis-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Sliders className="w-4 h-4" />
          </div>
          <div>
            <h2 id="scenario-analysis-heading" className="font-semibold text-sm text-slate-100">
              Interactive Scenario Sensitivity Analysis
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Stress-testing scoring parameters (baseline remains preserved)
            </span>
          </div>
        </div>

        <Badge variant="outline" size="sm">
          {scenarios.length} Scenarios Available
        </Badge>
      </div>

      {/* Scenario Selector Pills */}
      <div className="flex flex-wrap gap-1.5">
        {scenarios.map((sc, idx) => {
          const isSel = idx === selectedIdx;
          return (
            <button
              key={sc.name}
              onClick={() => setSelectedIdx(idx)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all border ${
                isSel
                  ? 'bg-emerald-600 text-white border-emerald-500 font-semibold shadow-sm'
                  : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 border-slate-800'
              }`}
            >
              {sc.name.replace(/_/g, ' ')}
            </button>
          );
        })}
      </div>

      {/* Selected Scenario Panel */}
      <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800/80 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
          <div>
            <span className="text-xs font-mono font-bold text-emerald-400 uppercase tracking-wide">
              {current.name.replace(/_/g, ' ')}
            </span>
            <p className="text-xs text-slate-300 font-sans mt-0.5">
              {current.parameters?.description || 'Modified scenario parameter perturbation.'}
            </p>
          </div>

          <div className="text-[11px] font-mono text-slate-400 shrink-0">
            Kind: {current.parameters?.kind} | Home Mult: {current.parameters?.home_mult}x | Away Mult: {current.parameters?.away_mult}x
          </div>
        </div>

        {/* Probability Comparison Bar */}
        <div className="space-y-1">
          <span className="text-xs font-mono text-slate-400 block">
            Perturbed 1X2 Probabilities:
          </span>
          <ProbabilityBar
            home={current.probabilities.home}
            draw={current.probabilities.draw}
            away={current.probabilities.away}
            homeTeamName={homeTeamName}
            awayTeamName={awayTeamName}
          />
        </div>

        {/* Changed Expected Goals & Probabilities Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
          <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
            <span className="text-xs font-mono text-slate-400 block">Scenario Home λ</span>
            <div className="text-xl font-mono font-bold text-blue-400 mt-0.5">
              {formatLambda(current.goals.home_lambda)}
            </div>
            {!isBaseline && (
              <span className="text-[10px] font-mono text-slate-400 block mt-0.5">
                Baseline: {formatLambda(baseline.goals.home_lambda)}
              </span>
            )}
          </div>

          <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
            <span className="text-xs font-mono text-slate-400 block">Scenario Away λ</span>
            <div className="text-xl font-mono font-bold text-emerald-400 mt-0.5">
              {formatLambda(current.goals.away_lambda)}
            </div>
            {!isBaseline && (
              <span className="text-[10px] font-mono text-slate-400 block mt-0.5">
                Baseline: {formatLambda(baseline.goals.away_lambda)}
              </span>
            )}
          </div>

          <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
            <span className="text-xs font-mono text-slate-400 block">Combined Total λ</span>
            <div className="text-xl font-mono font-bold text-purple-400 mt-0.5">
              {formatLambda(current.goals.total_lambda)}
            </div>
            {!isBaseline && (
              <span className="text-[10px] font-mono text-slate-400 block mt-0.5">
                Baseline: {formatLambda(baseline.goals.total_lambda)}
              </span>
            )}
          </div>
        </div>

        {/* Delta from Baseline */}
        {!isBaseline && diff && (
          <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-wrap items-center justify-between text-xs font-mono gap-3">
            <span className="text-slate-400 font-semibold">Shift from baseline:</span>
            <div className="flex items-center gap-4">
              <span className={diff.home > 0 ? 'text-blue-400' : 'text-slate-300'}>
                Home: {diff.home > 0 ? `+${(diff.home * 100).toFixed(1)}%` : `${(diff.home * 100).toFixed(1)}%`}
              </span>
              <span className={diff.draw > 0 ? 'text-blue-400' : 'text-slate-300'}>
                Draw: {diff.draw > 0 ? `+${(diff.draw * 100).toFixed(1)}%` : `${(diff.draw * 100).toFixed(1)}%`}
              </span>
              <span className={diff.away > 0 ? 'text-emerald-400' : 'text-slate-300'}>
                Away: {diff.away > 0 ? `+${(diff.away * 100).toFixed(1)}%` : `${(diff.away * 100).toFixed(1)}%`}
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="text-[11px] text-slate-400 font-sans">
        {current.label || 'Scenario sensitivity analysis tests mathematical elasticity and does not predict future real-world conditions.'}
      </div>
    </section>
  );
};
