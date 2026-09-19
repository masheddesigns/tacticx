import React from 'react';
import { HelpCircle, Shield, AlertCircle, CheckCircle } from 'lucide-react';
import { UncertaintySection as UncertaintyData, TemporalQualitySection } from '../../api/types';
import { Badge } from '../common/Badge';

export interface UncertaintySectionProps {
  uncertainty: UncertaintyData;
  temporalQuality?: TemporalQualitySection;
}

export const UncertaintySection: React.FC<UncertaintySectionProps> = ({
  uncertainty,
  temporalQuality,
}) => {
  const completeness = uncertainty.data_completeness || {};
  const entropy = uncertainty.predictive_entropy;
  const margin = uncertainty.probability_margin;
  const topProb = uncertainty.top_probability;

  const strictCount = temporalQuality?.strict?.length || 0;
  const estimatedCount = temporalQuality?.estimated?.length || 0;
  const unknownCount = temporalQuality?.unknown?.length || 0;

  return (
    <section aria-labelledby="uncertainty-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
            <HelpCircle className="w-4 h-4" />
          </div>
          <div>
            <h2 id="uncertainty-heading" className="font-semibold text-sm text-slate-100">
              Uncertainty & Data Completeness Diagnostics
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Distinct informational dimensions (never collapsed into a single confidence rating)
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Predictive Entropy */}
        <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1">
          <span className="text-xs font-mono text-slate-400 block">Predictive Entropy</span>
          <div className="text-xl font-mono font-bold text-slate-100">
            {entropy !== undefined && entropy !== null ? entropy.toFixed(4) : '—'}
          </div>
          <span className="text-[10px] text-slate-400 font-sans block">
            Shannon entropy over 3 outcomes (Max ~1.0986 nats)
          </span>
        </div>

        {/* Probability Margin */}
        <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1">
          <span className="text-xs font-mono text-slate-400 block">Top Margin Separation</span>
          <div className="text-xl font-mono font-bold text-slate-100">
            {margin !== undefined && margin !== null ? margin.toFixed(4) : '—'}
          </div>
          <span className="text-[10px] text-slate-400 font-sans block">
            Gap between 1st and 2nd probability options
          </span>
        </div>

        {/* Sample History Completeness */}
        <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1">
          <span className="text-xs font-mono text-slate-400 block">Sample History Depth</span>
          <div className="text-base font-mono font-bold text-slate-100">
            H: {completeness.home_history ?? 0} | A: {completeness.away_history ?? 0} matches
          </div>
          <span className="text-[10px] text-slate-400 font-sans block">
            Pre-cutoff finished fixtures contributing to model ratings
          </span>
        </div>

        {/* Temporal Audit Classification */}
        <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1">
          <span className="text-xs font-mono text-slate-400 block">Temporal Classification</span>
          <div className="flex items-center gap-1.5 pt-0.5">
            <Badge variant={strictCount > 0 ? 'success' : 'default'} size="sm">
              {strictCount} Strict
            </Badge>
            <Badge variant={estimatedCount > 0 ? 'warning' : 'outline'} size="sm">
              {estimatedCount} Est
            </Badge>
            <Badge variant={unknownCount > 0 ? 'default' : 'outline'} size="sm">
              {unknownCount} Unk
            </Badge>
          </div>
          <span className="text-[10px] text-slate-400 font-sans block">
            Feature timestamps verification status
          </span>
        </div>
      </div>

      <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-start gap-2 text-xs text-slate-400 font-sans">
        <Shield className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <p className="leading-relaxed text-[11px]">
          {uncertainty.note ||
            'Probability, uncertainty, and data completeness are independent analytical concepts; high certainty or complete data is an observation of model consensus, never a correctness guarantee.'}
        </p>
      </div>
    </section>
  );
};
