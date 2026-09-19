import React from 'react';
import { ShieldAlert, GitCommit } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="w-full border-t border-surface-border bg-surface-base py-6 text-xs text-slate-500 font-sans mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-slate-400">
          <ShieldAlert className="w-4 h-4 text-slate-500 shrink-0" aria-hidden="true" />
          <p className="text-[11px] leading-relaxed">
            <strong className="font-semibold text-slate-300">Analytical Disclaimer:</strong> TacticX is a deterministic football intelligence platform providing objective model probabilities, expected goal rates, and market comparison. Strictly no betting execution, wagering advice, or guaranteed outcomes.
          </p>
        </div>
        <div className="flex items-center gap-4 text-[11px] font-mono text-slate-500 shrink-0">
          <span className="flex items-center gap-1">
            <GitCommit className="w-3.5 h-3.5" />
            Commit: 5b6b8b1
          </span>
          <span>•</span>
          <span>Phase 21 Product UI</span>
        </div>
      </div>
    </footer>
  );
};
