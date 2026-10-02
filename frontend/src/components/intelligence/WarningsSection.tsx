import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, Info, ShieldAlert } from 'lucide-react';
import { WarningItem } from '../../api/types';
import { Badge } from '../common/Badge';

export interface WarningsSectionProps {
  warnings: WarningItem[];
  defaultOpen?: boolean;
}

export const WarningsSection: React.FC<WarningsSectionProps> = ({ warnings, defaultOpen = true }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);


  if (!warnings || warnings.length === 0) {
    return null;
  }

  const getSeverityBadgeVariant = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'error':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  };

  const getHumanFriendlyExplanation = (code: string): string => {
    switch (code) {
      case 'HISTORICAL_DATA_SPARSE':
        return 'Teams have fewer historical matches recorded before kickoff. Model applies cautious Bayesian shrinkage towards league average rather than relying on noisy small samples.';
      case 'MODEL_DISAGREEMENT_HIGH':
        return 'Individual sub-models (Poisson goal rate vs Elo rating) disagree on the margin. The ensemble model combines both perspectives to prevent overconfidence.';
      default:
        return 'System data quality check completed prior to kickoff calculation.';
    }
  };

  return (
    <section
      aria-labelledby="warnings-heading"
      className="rounded-xl border border-amber-900/40 bg-amber-950/10 shadow-sm overflow-hidden transition-all"
    >
      {/* Header bar that can toggle expansion */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-3.5 px-4 text-left hover:bg-amber-950/20 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <h2 id="warnings-heading" className="font-semibold text-xs font-mono text-amber-200">
            System Ingestion & Calibration Notices ({warnings.length})
          </h2>
          <span className="text-[11px] text-slate-400 font-sans hidden sm:inline">
            — Audit diagnostics & Bayesian regularization active
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-amber-400 font-medium">
            {isOpen ? 'Hide Details' : 'View Audit Details'}
          </span>
          {isOpen ? (
            <ChevronUp className="w-4 h-4 text-amber-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-amber-400" />
          )}
        </div>
      </button>

      {/* Expanded body with clean human-friendly explanations and formatted audit evidence */}
      {isOpen && (
        <div className="p-4 pt-1 space-y-3 border-t border-amber-900/30">
          {warnings.map((w, idx) => {
            const isWarning = w.severity === 'warning' || w.severity === 'error';
            const explanation = getHumanFriendlyExplanation(w.code);

            return (
              <div
                key={idx}
                className={`p-3.5 rounded-lg border text-xs font-mono space-y-2.5 ${
                  isWarning
                    ? 'bg-slate-900/90 border-slate-800 text-slate-300'
                    : 'bg-slate-950/60 border-slate-800 text-slate-400'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={getSeverityBadgeVariant(w.severity)} size="sm">
                      {w.severity.toUpperCase()}
                    </Badge>
                    <span className="font-bold text-slate-100">{w.code}</span>
                  </div>
                  <span className="text-[11px] text-slate-400 font-sans">
                    {w.message || w.detail}
                  </span>
                </div>

                {/* Human-friendly translation of the warning */}
                <div className="flex items-start gap-2 p-2.5 rounded bg-slate-950/80 border border-slate-800 text-xs text-slate-300 font-sans leading-relaxed">
                  <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                  <span>
                    <strong className="text-white">What this means:</strong> {explanation}
                  </span>
                </div>


              {w.evidence && Object.keys(w.evidence).length > 0 && (
                <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 font-mono">
                  <span className="font-semibold text-slate-400 block mb-1">Audit Evidence:</span>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(w.evidence).map(([key, val]) => {
                      const formatVal = (v: unknown): string => {
                        if (v == null) return 'null';
                        if (Array.isArray(v)) return v.map(formatVal).join(', ');
                        if (typeof v === 'number') return v.toFixed(3);
                        if (typeof v === 'object') {
                          return Object.entries(v as Record<string, unknown>)
                            .map(([subKey, subVal]) => {
                              if (typeof subVal === 'object' && subVal !== null) {
                                // For deeper objects like home: { mean: 0.68, range: 0.25 }
                                const summary = Object.entries(subVal as Record<string, unknown>)
                                  .filter(([k]) => ['mean', 'std', 'min', 'max', 'range'].includes(k))
                                  .map(([k, sv]) => `${k}=${typeof sv === 'number' ? sv.toFixed(2) : String(sv)}`)
                                  .join(' ');
                                return `${subKey}: (${summary || JSON.stringify(subVal)})`;
                              }
                              return `${subKey}: ${typeof subVal === 'number' ? subVal.toFixed(3) : String(subVal)}`;
                            })
                            .join(' · ');
                        }
                        return String(v);
                      };

                      return (
                        <div key={key} className="px-2 py-1 rounded bg-slate-950 border border-slate-800 text-[11px] leading-relaxed">
                          <span className="text-slate-400 font-semibold">{key}: </span>
                          <span className="text-slate-300 font-mono">{formatVal(val)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    )}
  </section>
);
};

