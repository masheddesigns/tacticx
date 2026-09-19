import React from 'react';
import { AlertCircle, ShieldOff, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export interface CurrentSeasonBannerProps {
  currentSeason?: string;
  leaguesCoverage?: Record<string, any>;
}

export const CurrentSeasonBanner: React.FC<CurrentSeasonBannerProps> = ({
  currentSeason = '2026/27',
  leaguesCoverage = {},
}) => {
  const primaryLeagues = ['EPL', 'LA_LIGA', 'SERIE_A', 'BUNDESLIGA', 'LIGUE_1'];

  return (
    <section aria-labelledby="current-season-notice-title" className="rounded-xl border border-amber-800/40 bg-gradient-to-br from-amber-950/30 via-slate-900/60 to-slate-900/80 p-5 shadow-lg backdrop-blur-sm">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 mt-0.5 shrink-0">
            <ShieldOff className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800/60">
                Data Transparency
              </span>
              <span className="text-xs font-mono text-slate-400">Season: {currentSeason}</span>
            </div>
            <h2 id="current-season-notice-title" className="text-base font-semibold text-slate-100 mt-1">
              Current-Season Fixture Source Unavailable
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl leading-relaxed">
              No validated Level-A provider currently supplies real-time fixtures for the {currentSeason} campaign. In accordance with TacticX architectural safety guidelines, unverified fixtures and synthetic probabilities are strictly prohibited. Historical matches and frozen model intelligence remain fully operational.
            </p>
          </div>
        </div>

        <Link
          to="/system"
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-mono font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors shrink-0"
        >
          <span>Provider Qualification</span>
          <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
        </Link>
      </div>

      {/* Honest 0-coverage telemetry table */}
      <div className="mt-4 pt-4 border-t border-slate-800/80 grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
        {primaryLeagues.map((code) => {
          const count = leaguesCoverage[code]?.fixture_count ?? 0;
          return (
            <div key={code} className="p-2.5 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-[11px] font-mono text-slate-400 block">{code.replace('_', ' ')}</span>
              <span className="text-sm font-mono font-bold text-amber-400 mt-0.5 block">
                {count} fixtures
              </span>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Coverage: 0.0%</span>
            </div>
          );
        })}
      </div>
    </section>
  );
};
