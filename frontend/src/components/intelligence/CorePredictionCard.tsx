import React from 'react';
import { Percent, Cpu, Clock, ShieldCheck } from 'lucide-react';
import { CorePredictionSection, CutoffSection } from '../../api/types';
import { formatProbability } from '../../lib/utils';
import { ProbabilityBar } from './ProbabilityBar';
import { Badge } from '../common/Badge';

export interface CorePredictionCardProps {
  prediction: CorePredictionSection;
  cutoff?: CutoffSection;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const CorePredictionCard: React.FC<CorePredictionCardProps> = ({
  prediction,
  cutoff,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  return (
    <section aria-labelledby="core-prediction-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Percent className="w-4 h-4" />
          </div>
          <div>
            <h2 id="core-prediction-heading" className="font-semibold text-sm text-slate-100">Core 1X2 Probabilities</h2>
            <span className="text-[11px] font-mono text-slate-400">Neutral statistical model estimates</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {prediction.model_version && (
            <Badge variant="outline" size="sm">
              <Cpu className="w-3 h-3" />
              {prediction.model_version}
            </Badge>
          )}
          {prediction.calibration_state && (
            <Badge
              variant={prediction.calibration_state === 'calibrated' ? 'success' : 'default'}
              size="sm"
            >
              {prediction.calibration_state}
            </Badge>
          )}
        </div>
      </div>

      {/* Probability Visual Bar */}
      <ProbabilityBar
        home={prediction.home}
        draw={prediction.draw}
        away={prediction.away}
        homeTeamName={homeTeamName}
        awayTeamName={awayTeamName}
      />

      {/* 3 Outcome Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3.5 rounded-lg bg-slate-900/80 border border-blue-900/40 text-center">
          <span className="text-[11px] font-mono text-blue-400 uppercase tracking-wider block">
            Home ({homeTeamName})
          </span>
          <div className="text-xl sm:text-2xl font-mono font-bold text-slate-100 mt-1">
            {formatProbability(prediction.home)}
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">
            Model probability
          </span>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-700/60 text-center">
          <span className="text-[11px] font-mono text-slate-300 uppercase tracking-wider block">
            Draw
          </span>
          <div className="text-xl sm:text-2xl font-mono font-bold text-slate-100 mt-1">
            {formatProbability(prediction.draw)}
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">
            Model probability
          </span>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-900/80 border border-emerald-900/40 text-center">
          <span className="text-[11px] font-mono text-emerald-400 uppercase tracking-wider block">
            Away ({awayTeamName})
          </span>
          <div className="text-xl sm:text-2xl font-mono font-bold text-slate-100 mt-1">
            {formatProbability(prediction.away)}
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">
            Model probability
          </span>
        </div>
      </div>

      {/* Technical Footnote: Mode & Cutoff */}
      <div className="pt-3 border-t border-surface-border/80 flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 gap-2">
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
          <span>Mode: {prediction.prediction_mode || 'strict_prematch'}</span>
        </div>
        {cutoff?.prediction_as_of && (
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Audit point: {cutoff.prediction_as_of}</span>
          </div>
        )}
      </div>
    </section>
  );
};
