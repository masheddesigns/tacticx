import React from 'react';
import { Shield, Clock, MapPin, Calendar, Layers } from 'lucide-react';
import { MatchSection, CutoffSection } from '../../api/types';
import { formatDateTime } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface MatchHeaderProps {
  match: MatchSection;
  cutoff?: CutoffSection;
}

export const MatchHeader: React.FC<MatchHeaderProps> = ({ match, cutoff }) => {
  const kickoff = formatDateTime(match.kickoff);
  const homeName = match.home_team?.name || 'Home Team';
  const awayName = match.away_team?.name || 'Away Team';
  const compName = match.competition?.name || match.competition?.code || 'Football League';

  return (
    <div className="rounded-xl border border-surface-border bg-gradient-to-b from-surface-card to-slate-900/90 p-6 shadow-md">
      {/* Top bar: Competition, Season, Status */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-surface-border">
        <div className="flex items-center gap-2.5">
          <Badge variant="purple" size="md">
            {compName}
          </Badge>
          {match.season && (
            <span className="text-xs font-mono text-slate-400">
              Season {match.season}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Badge
            variant={
              match.status === 'LIVE' ? 'error' : match.status === 'FINISHED' ? 'default' : 'info'
            }
            size="md"
          >
            {match.status}
          </Badge>
          <span className="text-xs font-mono text-slate-400">Match #{match.match_id}</span>
        </div>
      </div>

      {/* Hero Teams Display */}
      <div className="py-6 flex flex-col md:flex-row items-center justify-between gap-6 text-center md:text-left">
        <div className="flex-1 min-w-0">
          <span className="text-xs uppercase tracking-wider font-mono text-slate-400 block mb-1">
            Home Team
          </span>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100 truncate" title={homeName}>
            {homeName}
          </h1>
        </div>

        <div className="flex flex-col items-center justify-center px-4 shrink-0">
          <span className="text-xs font-mono font-bold text-emerald-400 uppercase tracking-widest px-3 py-1 rounded bg-slate-950/80 border border-slate-800">
            VS
          </span>
          <div className="mt-2 flex items-center gap-1.5 text-xs font-mono text-slate-400">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>{kickoff.full}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0 text-center md:text-right">
          <span className="text-xs uppercase tracking-wider font-mono text-slate-400 block mb-1">
            Away Team
          </span>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100 truncate" title={awayName}>
            {awayName}
          </h1>
        </div>
      </div>

      {/* Metadata Footnote: Sources & Cutoff */}
      <div className="pt-4 border-t border-surface-border flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400 font-mono">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-slate-500" />
          <span>Ingested Sources:</span>
          {match.sources?.length > 0 ? (
            match.sources.map((s, idx) => (
              <span key={idx} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px]">
                {s.source}
              </span>
            ))
          ) : (
            <span className="text-slate-400">Canonical store</span>
          )}
        </div>

        {cutoff?.cutoff && (
          <div className="flex items-center gap-1.5 text-slate-400">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Cutoff: {cutoff.cutoff}</span>
          </div>
        )}
      </div>
    </div>
  );
};
