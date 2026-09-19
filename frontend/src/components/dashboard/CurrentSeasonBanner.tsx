import React from 'react';
import { AlertCircle, ShieldOff, ArrowRight, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';

export interface LeagueCoverageItem {
  competition?: string;
  fixture_count?: number | null;
  activation_status?: string;
  qualification_level?: string;
  coverage_measurable?: boolean;
  eligible_for_activation?: boolean;
  blocking_reasons?: string[];
}

export interface CurrentSeasonBannerProps {
  currentSeason?: string;
  leaguesCoverage?: Record<string, any>;
  readinessItems?: LeagueCoverageItem[];
}

export const CurrentSeasonBanner: React.FC<CurrentSeasonBannerProps> = ({
  currentSeason = '2026/27',
  leaguesCoverage = {},
  readinessItems = [],
}) => {
  const primaryLeagues = ['EPL', 'LA_LIGA', 'SERIE_A', 'BUNDESLIGA', 'LIGUE_1'];

  // Map readiness items by competition for quick lookup
  const itemsByComp: Record<string, LeagueCoverageItem> = {};
  for (const item of readinessItems) {
    if (item.competition) {
      itemsByComp[item.competition] = item;
    }
  }

  const anyActive = primaryLeagues.some(
    (c) => (itemsByComp[c]?.activation_status || leaguesCoverage[c]?.activation_status) === 'ACTIVE'
  );

  return (
    <section aria-labelledby="current-season-notice-title" className="rounded-xl border border-amber-800/40 bg-gradient-to-br from-amber-950/30 via-slate-900/60 to-slate-900/80 p-5 shadow-lg backdrop-blur-sm">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className={`p-2 rounded-lg ${anyActive ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-amber-500/10 border-amber-500/20 text-amber-400'} border mt-0.5 shrink-0`}>
            {anyActive ? <CheckCircle2 className="w-5 h-5" aria-hidden="true" /> : <ShieldOff className="w-5 h-5" aria-hidden="true" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={`text-[11px] font-mono uppercase tracking-wider px-2 py-0.5 rounded ${anyActive ? 'bg-emerald-950 text-emerald-400 border-emerald-800/60' : 'bg-amber-950 text-amber-400 border-amber-800/60'} border`}>
                Data Transparency
              </span>
              <span className="text-xs font-mono text-slate-400">Season: {currentSeason}</span>
            </div>
            <h2 id="current-season-notice-title" className="text-base font-semibold text-slate-100 mt-1">
              {anyActive ? 'Current-Season Controlled Acquisition Active' : 'Current-Season Fixture Source Unavailable'}
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl leading-relaxed">
              {anyActive
                ? `Current-season ingestion is active for authorized competitions in the ${currentSeason} campaign. Prediction snapshots and match intelligence remain strictly governed by kickoff locks and temporal safety.`
                : `No validated Level-A provider currently supplies real-time fixtures for the ${currentSeason} campaign. In accordance with TacticX architectural safety guidelines, unverified fixtures and synthetic probabilities are strictly prohibited. Historical matches and frozen model intelligence remain fully operational.`}
            </p>
          </div>
        </div>

        <Link
          to="/system"
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-mono font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors shrink-0"
        >
          <span>Provider Qualification & Readiness</span>
          <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
        </Link>
      </div>

      {/* Honest 0-coverage & dynamic activation telemetry */}
      <div className="mt-4 pt-4 border-t border-slate-800/80 grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
        {primaryLeagues.map((code) => {
          const item = itemsByComp[code];
          const legacy = leaguesCoverage[code];
          const status = item?.activation_status || legacy?.activation_status || 'UNAVAILABLE';
          const isMeasurable = item ? (item.coverage_measurable ?? false) : true;
          const fixtureCount = item?.fixture_count ?? legacy?.fixture_count ?? 0;

          let badgeColor = 'text-amber-400 border-amber-800/60 bg-amber-950/40';
          let statusLabel = 'Unavailable';
          let coverageText = isMeasurable ? 'Coverage: 0.0%' : 'N/A - Provider Unavailable';

          if (status === 'ACTIVE') {
            badgeColor = 'text-emerald-400 border-emerald-800/60 bg-emerald-950/40';
            statusLabel = 'Active';
            coverageText = `${fixtureCount} fixtures active`;
          } else if (status === 'QUALIFIED') {
            badgeColor = 'text-sky-400 border-sky-800/60 bg-sky-950/40';
            statusLabel = 'Qualified (Awaiting Activation)';
            coverageText = 'Awaiting Activation';
          } else if (status === 'DEGRADED') {
            badgeColor = 'text-rose-400 border-rose-800/60 bg-rose-950/40';
            statusLabel = 'Degraded';
            coverageText = 'Provider Degraded';
          } else {
            // UNAVAILABLE
            badgeColor = 'text-amber-400 border-amber-800/60 bg-amber-950/40';
            statusLabel = 'Unavailable';
            coverageText = isMeasurable ? 'Coverage: 0.0%' : 'N/A - Provider Unavailable';
          }

          return (
            <div key={code} className="p-2.5 rounded bg-slate-900/60 border border-slate-800 flex flex-col justify-between">
              <div>
                <span className="text-[11px] font-mono text-slate-400 block">{code.replace('_', ' ')}</span>
                <span className="text-sm font-mono font-bold text-amber-400 mt-0.5 block">
                  {fixtureCount} fixtures
                </span>
              </div>
              <div className="mt-2 pt-1.5 border-t border-slate-800/50">
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border block truncate ${badgeColor}`}>
                  {statusLabel}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block truncate">
                  {coverageText}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};

