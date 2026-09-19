import React from 'react';
import { FileText, Cpu, CheckCircle, Database } from 'lucide-react';
import { ExplanationSection as ExplanationData } from '../../api/types';

export interface ExplanationSectionProps {
  explanation: ExplanationData;
}

export const ExplanationSection: React.FC<ExplanationSectionProps> = ({ explanation }) => {
  const headline = explanation.headline;
  const factors = explanation.factors || [];

  return (
    <section aria-labelledby="explanation-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex items-center gap-2 pb-3 border-b border-surface-border">
        <div className="p-1.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">
          <FileText className="w-4 h-4" />
        </div>
        <div>
          <h2 id="explanation-heading" className="font-semibold text-sm text-slate-100">
            Model Explanation & Input Breakdown
          </h2>
          <span className="text-[11px] font-mono text-slate-400">
            Transparent breakdown generated directly by the backend composer
          </span>
        </div>
      </div>

      {headline && (
        <div className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs text-slate-200 leading-relaxed font-sans">
          <span className="font-semibold text-emerald-400 font-mono text-[11px] block mb-1 uppercase tracking-wider">
            Summary:
          </span>
          {headline}
        </div>
      )}

      {factors.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-mono font-semibold text-slate-300 block">
            Supporting Input Factors:
          </span>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {factors.map((f, idx) => (
              <div key={idx} className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-slate-200 uppercase">
                    {f.factor.replace(/_/g, ' ')}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400 truncate max-w-[140px]" title={f.source}>
                    {f.source}
                  </span>
                </div>
                <p className="text-xs text-slate-300 font-sans leading-relaxed">
                  {f.statement}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {explanation.model_disagreement_note && (
        <div className="text-[11px] font-mono text-slate-400 pt-2 border-t border-slate-800/80">
          Note: {explanation.model_disagreement_note}
        </div>
      )}
    </section>
  );
};
