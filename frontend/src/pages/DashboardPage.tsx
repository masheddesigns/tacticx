import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Activity, Database, Calendar, ArrowRight, Clock, AlertTriangle } from 'lucide-react';
import {
  useJobDashboard,
  useSources,
  useAcquisitionStatus,
  useUpcomingMatches,
  useMatches,
  useReadyProbe,
} from '../api/queries';
import { CurrentSeasonBanner } from '../components/dashboard/CurrentSeasonBanner';
import { CompetitionCards, CompetitionData } from '../components/dashboard/CompetitionCards';
import { MatchRow } from '../components/matches/MatchRow';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';
import { Badge } from '../components/common/Badge';

export const DashboardPage: React.FC = () => {
  const { data: dashboard, isLoading: dashLoading, error: dashError } = useJobDashboard();
  const { data: sourcesData } = useSources();
  const { data: acqStatus } = useAcquisitionStatus();
  const { data: readyProbe } = useReadyProbe();
  const { data: upcomingData, isLoading: upLoading } = useUpcomingMatches(168);
  const { data: recentData, isLoading: recentLoading } = useMatches({ status: 'FINISHED', page_size: 5 });

  if (dashLoading && upLoading) {
    return <LoadingSpinner label="Loading TacticX System Dashboard..." />;
  }

  if (dashError) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <ErrorCard error={dashError as Error} title="Dashboard Telemetry Unavailable" />
      </div>
    );
  }

  // Competitions data extraction
  const competitionsMap = dashboard?.competitions || {};
  const primaryCompetitions: CompetitionData[] = [
    {
      code: 'EPL',
      name: 'Premier League',
      season: '2023/24 Historical',
      fixtureCount: competitionsMap['EPL']?.fixture_count || 0,
      upcomingCount: competitionsMap['EPL']?.upcoming || 0,
      latestObservation: competitionsMap['EPL']?.latest_observation,
    },
    {
      code: 'LA_LIGA',
      name: 'La Liga',
      season: '2023/24 Historical',
      fixtureCount: competitionsMap['LA_LIGA']?.fixture_count || 0,
      upcomingCount: competitionsMap['LA_LIGA']?.upcoming || 0,
      latestObservation: competitionsMap['LA_LIGA']?.latest_observation,
    },
    {
      code: 'SERIE_A',
      name: 'Serie A',
      season: '2023/24 Historical',
      fixtureCount: competitionsMap['SERIE_A']?.fixture_count || 0,
      upcomingCount: competitionsMap['SERIE_A']?.upcoming || 0,
      latestObservation: competitionsMap['SERIE_A']?.latest_observation,
    },
    {
      code: 'BUNDESLIGA',
      name: 'Bundesliga',
      season: '2023/24 Historical',
      fixtureCount: competitionsMap['BUNDESLIGA']?.fixture_count || 0,
      upcomingCount: competitionsMap['BUNDESLIGA']?.upcoming || 0,
      latestObservation: competitionsMap['BUNDESLIGA']?.latest_observation,
    },
    {
      code: 'LIGUE_1',
      name: 'Ligue 1',
      season: '2023/24 Historical',
      fixtureCount: competitionsMap['LIGUE_1']?.fixture_count || 0,
      upcomingCount: competitionsMap['LIGUE_1']?.upcoming || 0,
      latestObservation: competitionsMap['LIGUE_1']?.latest_observation,
    },
  ];

  const totalFixtures = Object.values(competitionsMap).reduce(
    (sum, c) => sum + (c.fixture_count || 0),
    0
  );

  const upcomingMatches = upcomingData?.data || [];
  const recentMatches = recentData?.data || [];
  const registeredSourcesCount = sourcesData?.sources?.length || 0;
  const isEngineReady = readyProbe?.status === 'ok';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Top Welcome & KPI Summary */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2.5">
              <span>TacticX Intelligence Engine</span>
              <Badge variant={isEngineReady ? 'success' : 'warning'} size="sm">
                {isEngineReady ? 'Validated Level-A Stack' : 'Degraded Cache/DB'}
              </Badge>
            </h1>
            <p className="text-xs text-slate-400 font-sans mt-1">
              Deterministic predictive intelligence, bivariate Poisson calibration, and operational provider monitoring.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/matches"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-mono font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-sm"
            >
              <span>Explore Fixtures</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* System KPIs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Total Fixtures Recorded</span>
            <div className="text-2xl font-mono font-bold text-slate-100">{totalFixtures}</div>
            <span className="text-[10px] text-slate-400 font-sans block">Historical canonical store</span>
          </div>

          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Current-Season Fixtures</span>
            <div className="text-2xl font-mono font-bold text-amber-400">0</div>
            <span className="text-[10px] text-slate-400 font-sans block">Level-A source unavailable</span>
          </div>

          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Registered Sources</span>
            <div className="text-2xl font-mono font-bold text-slate-100">{registeredSourcesCount}</div>
            <span className="text-[10px] text-slate-400 font-sans block">Multi-tier provider registry</span>
          </div>

          <div className="p-4 rounded-xl border border-surface-border bg-surface-card space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Active Scheduler Jobs</span>
            <div className="text-2xl font-mono font-bold text-emerald-400">
              {dashboard?.jobs ? Object.keys(dashboard.jobs).length : 0}
            </div>
            <span className="text-[10px] text-slate-400 font-sans block">Automated polling cadence</span>
          </div>
        </div>
      </div>

      {/* Mandatory Honest Zero-Data Current Season Notice */}
      <CurrentSeasonBanner
        currentSeason={acqStatus?.coverage?.current_season || '2026/27'}
        leaguesCoverage={competitionsMap}
      />

      {/* Competitions Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Supported Competitions Overview</span>
          </h2>
          <span className="text-xs font-mono text-slate-400">5 Top European Leagues</span>
        </div>

        <CompetitionCards competitions={primaryCompetitions} />
      </section>

      {/* Upcoming & Recent Fixtures Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upcoming Fixtures */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <Clock className="w-4 h-4 text-emerald-400" />
              <span>Upcoming Fixtures (Next 7 Days)</span>
            </h2>
            <span className="text-xs font-mono text-slate-400">{upcomingMatches.length} available</span>
          </div>

          <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden">
            {upcomingMatches.length === 0 ? (
              <div className="p-8 text-center space-y-2">
                <p className="text-xs font-mono text-slate-400">
                  No upcoming fixtures within the 168-hour window.
                </p>
                <p className="text-[11px] text-slate-400 font-sans max-w-sm mx-auto">
                  Because current-season coverage is currently 0, all analytical operations draw from completed historical seasons.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-surface-border">
                {upcomingMatches.slice(0, 4).map((m) => (
                  <MatchRow key={m.id} match={m} />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Recently Finished Matches with Intelligence */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-purple-400" />
              <span>Historical Intelligence Matches</span>
            </h2>
            <Link
              to="/matches"
              className="text-xs font-mono text-emerald-400 hover:text-emerald-300 font-medium"
            >
              View All
            </Link>
          </div>

          <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden">
            {recentMatches.length === 0 ? (
              <div className="p-8 text-center text-xs font-mono text-slate-400">
                No recent matches loaded.
              </div>
            ) : (
              <div className="divide-y divide-surface-border">
                {recentMatches.map((m) => (
                  <MatchRow key={m.id} match={m} />
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
