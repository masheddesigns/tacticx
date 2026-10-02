import React from 'react';
import { AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { WarningItem } from '../../api/types';
import { Badge } from '../common/Badge';

export interface WarningsSectionProps {
  warnings: WarningItem[];
}

export const WarningsSection: React.FC<WarningsSectionProps> = ({ warnings }) => {
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

  return (
    <section aria-labelledby="warnings-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-3">
      <div className="flex items-center gap-2 pb-2 border-b border-surface-border">
        <AlertTriangle className="w-4 h-4 text-amber-400" />
        <h2 id="warnings-heading" className="font-semibold text-sm text-slate-100">
          Backend Warnings & Ingestion Notices ({warnings.length})
        </h2>
      </div>

      <div className="space-y-2.5">
        {warnings.map((w, idx) => {
          const isWarning = w.severity === 'warning' || w.severity === 'error';

          return (
            <div
              key={idx}
              className={`p-3.5 rounded-lg border text-xs font-mono space-y-2 ${
                isWarning
                  ? 'bg-amber-950/20 border-amber-900/50 text-amber-200'
                  : 'bg-slate-900/60 border-slate-800 text-slate-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge variant={getSeverityBadgeVariant(w.severity)} size="sm">
                    {w.severity.toUpperCase()}
                  </Badge>
                  <span className="font-bold text-slate-100">{w.code}</span>
                </div>
              </div>

              <p className="font-sans text-xs text-slate-300 leading-relaxed">
                {w.message || w.detail}
              </p>

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
    </section>
  );
};
