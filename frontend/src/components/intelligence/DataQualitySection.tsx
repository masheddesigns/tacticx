import React from 'react';
import { CheckCircle2, XCircle, AlertCircle, Database, Layers } from 'lucide-react';
import { DataQualitySection as DataQualityData, TemporalQualitySection } from '../../api/types';
import { Badge } from '../common/Badge';

export interface DataQualitySectionProps {
  dataQuality: DataQualityData;
  temporalQuality?: TemporalQualitySection;
}

export const DataQualitySection: React.FC<DataQualitySectionProps> = ({
  dataQuality,
  temporalQuality,
}) => {
  const completeness = dataQuality.completeness || {};
  const coverage = dataQuality.coverage || {};
  const missingFamilies = dataQuality.missing_families || [];
  const sourceCount = dataQuality.source_count ?? 0;

  const coverageItems = [
    { label: 'xG (Expected Goals)', available: coverage.xg_available },
    { label: 'Event Data (Shots, Passes)', available: coverage.event_data_available },
    { label: 'Lineup Data', available: coverage.lineup_data_available },
    { label: 'Market Odds Data', available: coverage.market_available },
  ];

  return (
    <section aria-labelledby="data-quality-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <h2 id="data-quality-heading" className="font-semibold text-sm text-slate-100">
              Data Quality & Feature Availability
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Granular input telemetry (explicit statuses per feature family)
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="outline" size="sm">
            {sourceCount} Ingested Sources
          </Badge>
          <Badge variant={completeness.missing === 0 ? 'success' : 'default'} size="sm">
            {completeness.available ?? 0}/{completeness.feature_count ?? 0} Features Available
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Coverage Checks */}
        <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2.5">
          <span className="text-xs font-mono font-semibold text-slate-300 block">
            Family Ingestion Coverage
          </span>
          <div className="space-y-2 text-xs font-mono">
            {coverageItems.map((item) => (
              <div key={item.label} className="flex items-center justify-between py-1 border-b border-slate-800/80">
                <span className="text-slate-300">{item.label}</span>
                {item.available ? (
                  <span className="inline-flex items-center gap-1 text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Available
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-slate-400">
                    <XCircle className="w-3.5 h-3.5" />
                    Unavailable
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Temporal Quality Statuses */}
        <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2.5">
          <span className="text-xs font-mono font-semibold text-slate-300 block">
            Temporal Quality Breakdown
          </span>
          <div className="space-y-2 text-xs font-mono">
            <div className="flex items-start justify-between py-1 border-b border-slate-800/80">
              <span className="text-emerald-400 font-medium">Strict (Exact Pre-Cutoff):</span>
              <span className="text-slate-300 text-right">
                {temporalQuality?.strict?.length ? temporalQuality.strict.join(', ') : 'None'}
              </span>
            </div>
            <div className="flex items-start justify-between py-1 border-b border-slate-800/80">
              <span className="text-amber-400 font-medium">Estimated Timing:</span>
              <span className="text-slate-300 text-right">
                {temporalQuality?.estimated?.length ? temporalQuality.estimated.join(', ') : 'None'}
              </span>
            </div>
            <div className="flex items-start justify-between py-1">
              <span className="text-slate-400 font-medium">Unknown / Missing:</span>
              <span className="text-slate-400 text-right">
                {temporalQuality?.unknown?.length ? temporalQuality.unknown.join(', ') : 'None'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {missingFamilies.length > 0 && (
        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center gap-2 text-xs font-mono text-slate-400">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0" />
          <span>
            Excluded feature families: {missingFamilies.join(', ')}. In accordance with model design, missing features are treated as missing rather than assumed zero.
          </span>
        </div>
      )}
    </section>
  );
};
