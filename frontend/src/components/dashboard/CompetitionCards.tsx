import React from 'react';
import { Link } from 'react-router-dom';
import { Trophy, Calendar, Eye, ArrowUpRight } from 'lucide-react';
import { formatDateTime } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface CompetitionData {
  code: string;
  name: string;
  season?: string;
  fixtureCount: number;
  upcomingCount: number;
  latestObservation?: string | null;
}

export interface CompetitionCardsProps {
  competitions: CompetitionData[];
}

export const CompetitionCards: React.FC<CompetitionCardsProps> = ({ competitions }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {competitions.map((comp) => {
        const latest = formatDateTime(comp.latestObservation);
        const hasFixtures = comp.fixtureCount > 0;

        return (
          <div
            key={comp.code}
            className="rounded-xl border border-surface-border bg-surface-card p-5 flex flex-col justify-between hover:border-slate-700 transition-all shadow-sm"
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded bg-slate-800 border border-slate-700 text-slate-300">
                    <Trophy className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-sm text-slate-100">{comp.name}</h3>
                    <span className="text-[11px] font-mono text-slate-400">{comp.code}</span>
                  </div>
                </div>
                <Badge variant={hasFixtures ? 'success' : 'outline'}>
                  {comp.season || 'Historical'}
                </Badge>
              </div>

              <div className="mt-4 space-y-2 text-xs font-mono">
                <div className="flex items-center justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5 text-slate-400" /> Total Recorded:
                  </span>
                  <span className="text-slate-200 font-semibold">{comp.fixtureCount}</span>
                </div>

                <div className="flex items-center justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5 text-slate-400" /> Upcoming (24h-168h):
                  </span>
                  <span className={comp.upcomingCount > 0 ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
                    {comp.upcomingCount}
                  </span>
                </div>

                <div className="flex items-center justify-between py-1">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Eye className="w-3.5 h-3.5 text-slate-400" /> Latest Observation:
                  </span>
                  <span className="text-slate-300 text-[11px]" title={latest.full}>
                    {latest.date !== '—' ? latest.date : 'None'}
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-5 pt-3 border-t border-slate-800/80 flex items-center justify-between">
              <span className="text-[11px] text-slate-400 font-sans">
                {hasFixtures ? 'Intelligence available' : 'Awaiting provider'}
              </span>
              <Link
                to={`/matches?league=${encodeURIComponent(comp.code)}`}
                className="inline-flex items-center gap-1 text-xs font-mono text-emerald-400 hover:text-emerald-300 font-medium"
              >
                <span>Browse</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        );
      })}
    </div>
  );
};
