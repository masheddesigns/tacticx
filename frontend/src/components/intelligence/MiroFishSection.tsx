import React from 'react';
import { Fish, ShieldAlert, Cpu, CheckCircle, Info } from 'lucide-react';
import { MirofishSection as MirofishData } from '../../api/types';
import { Badge } from '../common/Badge';

export interface MiroFishSectionProps {
  mirofish: MirofishData;
}

export const MiroFishSection: React.FC<MiroFishSectionProps> = ({ mirofish }) => {
  const isOk = mirofish.status === 'ok';
  const scenario = mirofish.scenarios?.[0];

  return (
    <section aria-labelledby="mirofish-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
            <Fish className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 id="mirofish-heading" className="font-semibold text-sm text-slate-100">
                MiroFish Simulation Engine
              </h2>
              <span className="text-[10px] uppercase font-mono font-bold px-1.5 py-0.2 rounded bg-amber-950/80 text-amber-400 border border-amber-800">
                SIMULATED SCENARIO EVIDENCE
              </span>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              Qualitative scenario exploration (distinct from statistical probability engine)
            </span>
          </div>
        </div>

        <Badge variant={isOk ? 'success' : 'outline'} size="sm">
          {isOk ? 'Completed' : 'Unavailable'}
        </Badge>
      </div>

      {!isOk ? (
        <div className="p-6 text-center rounded-lg bg-slate-900/60 border border-slate-800 space-y-1.5">
          <span className="text-xs font-mono font-semibold text-slate-300 block">
            MiroFish provider is not configured.
          </span>
          <p className="text-[11px] text-slate-400 font-sans max-w-lg mx-auto leading-relaxed">
            {mirofish.reason ||
              'No external MiroFish scenario engine is bound to the backend environment. Statistical probabilities and expected goal calculations remain authoritative.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-slate-400 border-b border-slate-800 pb-2">
              <span>Provider: {mirofish.provider || 'default'}</span>
              <span>Contract: {mirofish.contract_version || 'v1'}</span>
            </div>

            {/* Escaped narrative text */}
            {scenario?.narrative && (
              <div className="space-y-1">
                <span className="text-xs font-mono font-semibold text-slate-300">
                  Simulation Narrative:
                </span>
                <p className="text-xs text-slate-200 font-sans leading-relaxed whitespace-pre-wrap bg-slate-950 p-3.5 rounded border border-slate-800">
                  {scenario.narrative}
                </p>
              </div>
            )}

            {/* Structured observations */}
            {scenario?.structured_observations && (
              <div className="space-y-2">
                <span className="text-xs font-mono font-semibold text-slate-300">
                  Key Qualitative Observations:
                </span>
                {Array.isArray(scenario.structured_observations) ? (
                  <div className="grid grid-cols-1 gap-2">
                    {scenario.structured_observations.map((obs: { kind?: string; statement?: string; detail?: Record<string, unknown> }, idx: number) => (
                      <div key={idx} className="p-3 rounded bg-slate-950 border border-slate-800 text-xs space-y-1.5">
                        {obs.kind && (
                          <span className={`inline-block px-1.5 py-0.5 rounded font-mono font-bold text-[10px] uppercase ${
                            obs.kind === 'sensitivity' ? 'bg-blue-950 text-blue-400 border border-blue-800' :
                            obs.kind === 'divergence' ? 'bg-amber-950 text-amber-400 border border-amber-800' :
                            obs.kind === 'caveat' ? 'bg-red-950 text-red-400 border border-red-800' :
                            'bg-slate-800 text-slate-300 border border-slate-700'
                          }`}>
                            {obs.kind}
                          </span>
                        )}
                        {obs.statement && (
                          <p className="text-slate-200 font-sans leading-relaxed">
                            {obs.statement}
                          </p>
                        )}
                        {obs.detail && Object.keys(obs.detail).length > 0 && (
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            {Object.entries(obs.detail).map(([dk, dv]) => (
                              <span key={dk} className="text-[10px] font-mono text-slate-500">
                                {dk}: <span className="text-slate-400">{typeof dv === 'object' ? JSON.stringify(dv) : String(dv)}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {Object.entries(scenario.structured_observations).map(([k, v]) => (
                      <div key={k} className="p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono">
                        <span className="text-slate-400 block">{k.replace(/_/g, ' ')}:</span>
                        <span className="text-slate-200 font-semibold">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Safety Notice */}
      <div className="flex items-start gap-2 p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-400 font-sans leading-relaxed">
        <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <span>
          MiroFish simulations are qualitative agentic stress-test scenarios. Outputs are strictly simulated hypotheses and are not converted into probability, confidence, or statistical evidence.
        </span>
      </div>
    </section>
  );
};
