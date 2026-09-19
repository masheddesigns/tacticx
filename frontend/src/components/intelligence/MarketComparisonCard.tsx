import React from 'react';
import { Scale, Clock, Users, AlertCircle } from 'lucide-react';
import { MarketSection } from '../../api/types';
import { formatProbability, formatDateTime } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface MarketComparisonCardProps {
  market: MarketSection;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const MarketComparisonCard: React.FC<MarketComparisonCardProps> = ({
  market,
  homeTeamName = 'Home',
  awayTeamName = 'Away',
}) => {
  const consensus = market.consensus || {};
  const modelProbs = market.model_probabilities || {};
  const divergence = market.divergence || {};
  const perOutcome = divergence.per_outcome || {};
  const marketTime = formatDateTime(market.market_timing);

  const hasMarket = market.market_status === 'ok' && market.bookmaker_count && market.bookmaker_count > 0;

  const outcomes = [
    { key: 'home', label: `Home (${homeTeamName})` },
    { key: 'draw', label: 'Draw' },
    { key: 'away', label: `Away (${awayTeamName})` },
  ];

  return (
    <section aria-labelledby="market-comparison-heading" className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Scale className="w-4 h-4" />
          </div>
          <div>
            <h2 id="market-comparison-heading" className="font-semibold text-sm text-slate-100">
              Market Consensus vs Model Alignment
            </h2>
            <span className="text-[11px] font-mono text-slate-400">
              Neutral divergence analysis against aggregated bookmaker consensus
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono">
          <Badge variant={hasMarket ? 'info' : 'outline'} size="sm">
            <Users className="w-3 h-3" />
            {market.bookmaker_count || 0} Bookmakers
          </Badge>
          {divergence.overall && (
            <Badge variant="default" size="sm">
              {divergence.overall.replace('_', ' ')}
            </Badge>
          )}
        </div>
      </div>

      {!hasMarket ? (
        <div className="p-6 text-center rounded-lg bg-slate-900/60 border border-slate-800 space-y-1">
          <span className="text-xs font-mono text-slate-300">
            No active pre-match market consensus recorded
          </span>
          <p className="text-[11px] text-slate-400 font-sans max-w-md mx-auto">
            Bookmaker odds were not observed prior to cutoff or this fixture uses historical dataset without contemporaneous odds.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
            {outcomes.map((item) => {
              const modelVal = (modelProbs as any)[item.key];
              const marketVal = (consensus as any)[item.key];
              const diff = (perOutcome as any)[item.key]?.absolute_difference;
              const magnitude = (perOutcome as any)[item.key]?.magnitude;

              return (
                <div key={item.key} className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-semibold text-slate-200">{item.label}</span>
                    {magnitude && (
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                        {magnitude.replace('_', ' ')}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
                    <div>
                      <span className="text-[10px] text-slate-400 block">Model:</span>
                      <span className="text-base font-bold text-slate-100">{formatProbability(modelVal)}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Market Consensus:</span>
                      <span className="text-base font-bold text-slate-300">{formatProbability(marketVal)}</span>
                    </div>
                  </div>

                  {diff !== undefined && (
                    <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] font-mono">
                      <span className="text-slate-400">Divergence:</span>
                      <span className={diff > 0 ? 'text-blue-400 font-semibold' : 'text-slate-300 font-semibold'}>
                        {diff > 0 ? `+${(diff * 100).toFixed(1)}%` : `${(diff * 100).toFixed(1)}%`}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 pt-1 border-t border-slate-800/60">
            {market.market_timing && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-slate-400" />
                Market snapshot: {marketTime.full}
              </span>
            )}
            <span>Benchmark mode: {market.closing_used ? 'Closing (ex-post)' : 'Pre-match live snapshot'}</span>
          </div>
        </div>
      )}

      <div className="text-[11px] text-slate-400 font-sans leading-relaxed">
        {divergence.note ||
          'Market divergence measures mathematical disagreement between statistical models and bookmaker consensus. Divergences are descriptive observations and do not constitute value, wagering edge, or staking recommendations.'}
      </div>
    </section>
  );
};
