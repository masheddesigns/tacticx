import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check, ShieldCheck, Terminal } from 'lucide-react';
import { ProvenanceSection as ProvenanceData } from '../../api/types';
import { copyToClipboard } from '../../lib/utils';

export interface ProvenanceSectionProps {
  provenance: ProvenanceData;
  rawJson?: any;
}

export const ProvenanceSection: React.FC<ProvenanceSectionProps> = ({
  provenance,
  rawJson,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopy = async () => {
    const textToCopy = rawJson
      ? JSON.stringify(rawJson, null, 2)
      : JSON.stringify(provenance, null, 2);

    const success = await copyToClipboard(textToCopy);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <section aria-labelledby="provenance-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 text-xs font-mono font-semibold text-slate-300 hover:text-slate-100 transition-colors focus:outline-none"
        >
          {isOpen ? <ChevronDown className="w-4 h-4 text-emerald-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
          <span id="provenance-heading">CRYPTOGRAPHIC PROVENANCE & ENGINE TELEMETRY</span>
        </button>

        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs font-mono bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-semibold">Copied JSON</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5 text-slate-400" />
              <span>Copy JSON</span>
            </>
          )}
        </button>
      </div>

      {isOpen && (
        <div className="pt-3 border-t border-slate-800 space-y-3 text-xs font-mono">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Response Hash (SHA-256)</span>
              <span className="text-slate-200 truncate block mt-0.5" title={provenance.response_hash}>
                {provenance.response_hash || 'None'}
              </span>
            </div>

            <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Model Version</span>
              <span className="text-slate-200 truncate block mt-0.5">
                {provenance.model_version || 'None'}
              </span>
            </div>

            <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Feature Version</span>
              <span className="text-slate-200 truncate block mt-0.5">
                {provenance.feature_version || 'None'}
              </span>
            </div>

            <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Dataset Version</span>
              <span className="text-slate-200 truncate block mt-0.5">
                {provenance.dataset_version || 'canonical_store'}
              </span>
            </div>

            <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Scenario Version</span>
              <span className="text-slate-200 truncate block mt-0.5">
                {provenance.scenario_version || 'None'}
              </span>
            </div>

            <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Generated Timestamp (UTC)</span>
              <span className="text-slate-200 truncate block mt-0.5">
                {provenance.generated_at || '—'}
              </span>
            </div>
          </div>

          <div className="p-3 rounded bg-slate-950 border border-slate-800 flex items-center gap-2 text-[11px] text-slate-400 font-sans">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              Deterministic cryptographic provenance confirms that this document was assembled without live leakages or subsequent post-cutoff modifications.
            </span>
          </div>
        </div>
      )}
    </section>
  );
};
