import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ShieldCheck,
  Activity,
  Database,
  Calendar,
  ArrowRight,
  Clock,
  Sparkles,
  Trophy,
  Search,
  RotateCcw,
  RefreshCw,
  Flame,
} from 'lucide-react';
import {
  useJobDashboard,
  useSources,
  useAcquisitionStatus,
  useUpcomingMatches,
  useMatches,
  useReadyProbe,
  useLeagues,
} from '../api/queries';
import { CurrentSeasonBanner } from '../components/dashboard/CurrentSeasonBanner';
import { CompetitionCards, CompetitionData } from '../components/dashboard/CompetitionCards';
import { MatchRow } from '../components/matches/MatchRow';
import { getLeagueMeta } from './MatchExplorerPage';
import { getRelativeDateLabel } from '../lib/utils';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';
import { Badge } from '../components/common/Badge';

export const DashboardPage: React.FC = () => {
  // FotMob Homepage Filter State
  const [selectedDate, setSelectedDate] = useState<string | undefined>('2026-10-02');
  const [selectedStatus, setSelectedStatus] = useState<string | undefined>(undefined);
  const [selectedLeague, setSelectedLeague] = useState<string | undefined>(undefined);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [timeZone, setTimeZone] = useState<'UTC' | 'local'>('UTC');

  const { data: dashboard, isLoading: dashLoading, error: dashError } = useJobDashboard();
  const { data: sourcesData } = useSources();
  const { data: acqStatus } = useAcquisitionStatus();
  const { data: readyProbe } = useReadyProbe();
  const { data: upcomingData } = useUpcomingMatches(168);
  const { data: leaguesData } = useLeagues();

  // Query live matches right now
  const { data: liveData, refetch: refetchLive } = useMatches({
    status: 'LIVE',
    page_size: 20,
  });

  // Query homepage matches for the selected date or live filter
  const {
    data: matchesData,
    isLoading: matchesLoading,
    error: matchesError,
    refetch: refetchMatches,
    isFetching: isMatchesFetching,
  } = useMatches({
    date: selectedDate,
    status: selectedStatus,
    league: selectedLeague,
    team: searchQuery || undefined,
    page_size: 50,
  });

  const availableLeagueCodes = leaguesData?.data?.map((l) => l.code) || [
    'EPL',
    'LA_LIGA',
    'SERIE_A',
    'BUNDESLIGA',
    'LIGUE_1',
    'UCL',
    'NATIONS_LEAGUE',
    'FRIENDLIES',
  ];

  const competitionsMap = dashboard?.competitions || {};
  const primaryCompetitions: CompetitionData[] = [
    {
      code: 'EPL',
      name: 'Premier League',
      season: '2026/27 Season',
      fixtureCount: competitionsMap['EPL']?.fixture_count || 0,
      upcomingCount: competitionsMap['EPL']?.upcoming || 0,
      latestObservation: competitionsMap['EPL']?.latest_observation,
    },
    {
      code: 'LA_LIGA',
      name: 'La Liga',
      season: '2023/24 Completed',
      fixtureCount: competitionsMap['LA_LIGA']?.fixture_count || 0,
      upcomingCount: competitionsMap['LA_LIGA']?.upcoming || 0,
      latestObservation: competitionsMap['LA_LIGA']?.latest_observation,
    },
    {
      code: 'SERIE_A',
      name: 'Serie A',
      season: '2023/24 Completed',
      fixtureCount: competitionsMap['SERIE_A']?.fixture_count || 0,
      upcomingCount: competitionsMap['SERIE_A']?.upcoming || 0,
      latestObservation: competitionsMap['SERIE_A']?.latest_observation,
    },
    {
      code: 'BUNDESLIGA',
      name: 'Bundesliga',
      season: '2023/24 Completed',
      fixtureCount: competitionsMap['BUNDESLIGA']?.fixture_count || 0,
      upcomingCount: competitionsMap['BUNDESLIGA']?.upcoming || 0,
      latestObservation: competitionsMap['BUNDESLIGA']?.latest_observation,
    },
    {
      code: 'LIGUE_1',
      name: 'Ligue 1',
      season: '2023/24 Completed',
      fixtureCount: competitionsMap['LIGUE_1']?.fixture_count || 0,
      upcomingCount: competitionsMap['LIGUE_1']?.upcoming || 0,
      latestObservation: competitionsMap['LIGUE_1']?.latest_observation,
    },
    {
      code: 'UCL',
      name: 'UEFA Champions League',
      season: '2024/25 Completed',
      fixtureCount: competitionsMap['UCL']?.fixture_count || 0,
      upcomingCount: competitionsMap['UCL']?.upcoming || 0,
      latestObservation: competitionsMap['UCL']?.latest_observation,
    },
    {
      code: 'NATIONS_LEAGUE',
      name: 'UEFA Nations League',
      season: '2026/27 Active Matchday',
      fixtureCount: competitionsMap['NATIONS_LEAGUE']?.fixture_count || 0,
      upcomingCount: competitionsMap['NATIONS_LEAGUE']?.upcoming || 0,
      latestObservation: competitionsMap['NATIONS_LEAGUE']?.latest_observation,
    },
    {
      code: 'FRIENDLIES',
      name: 'International Friendlies',
      season: '2026 Active Window',
      fixtureCount: competitionsMap['FRIENDLIES']?.fixture_count || 0,
      upcomingCount: competitionsMap['FRIENDLIES']?.upcoming || 0,
      latestObservation: competitionsMap['FRIENDLIES']?.latest_observation,
    },
  ];

  const totalFixtures = Object.values(competitionsMap).reduce(
    (sum, c) => sum + (c.fixture_count || 0),
    0
  );

  const isEngineReady = readyProbe?.status === 'ok';
  const liveMatches = liveData?.data || [];
  const homepageMatches = matchesData?.data || [];

  // Group homepage matches by League (FotMob standard)
  const leagueGroups = homepageMatches.reduce<Record<string, typeof homepageMatches>>((acc, m) => {
    const lKey = m.league_name || m.league_code || 'Other Competitions';
    if (!acc[lKey]) acc[lKey] = [];
    acc[lKey].push(m);
    return acc;
  }, {});

  const handleSelectLive = () => {
    setSelectedStatus('LIVE');
    setSelectedDate(undefined);
  };

  const handleSelectDay = (day: string) => {
    setSelectedDate(day);
    setSelectedStatus(undefined);
  };

  const handleResetFilters = () => {
    setSelectedDate('2026-10-02');
    setSelectedStatus(undefined);
    setSelectedLeague(undefined);
    setSearchQuery('');
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
      {dashError && <ErrorCard error={dashError as Error} title="Dashboard Telemetry Degraded" />}

      {/* 1. FotMob Top Match Header & KPI Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-surface-border/70">
        <div>
          <div className="flex items-center gap-2.5">
            <Trophy className="w-6 h-6 text-emerald-400" />
            <h1 className="text-2xl font-black tracking-tight text-white font-sans">
              Matches & Live Scores
            </h1>
            <Badge variant={isEngineReady ? 'success' : 'warning'} size="sm">
              {isEngineReady ? 'Live Level-A Sync' : 'Degraded'}
            </Badge>
          </div>
          <p className="text-xs text-slate-400 mt-0.5 font-sans">
            FotMob fixture center with real-time minutes, scores, mathematical market probabilities & MiroFish AI.
          </p>
        </div>

        {/* Quick Stats Badges */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
            <span className="text-rose-400 font-bold">{liveMatches.length}</span>
            <span className="text-slate-400">Live In-Play</span>
          </div>

          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono">
            <span className="text-emerald-400 font-bold">{totalFixtures}</span>
            <span className="text-slate-400 ml-1.5">Fixtures</span>
          </div>

          <button
            onClick={() => {
              refetchLive();
              refetchMatches();
            }}
            disabled={isMatchesFetching}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            title="Refresh Live Scores"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isMatchesFetching ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* 2. FotMob Date Ribbon & Filter Navigator */}
      <div className="rounded-2xl border border-surface-border bg-surface-card p-4 space-y-3.5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border/80">
          {/* Day Navigation Tabs */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={handleSelectLive}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center gap-1.5 shadow-sm ${
                selectedStatus === 'LIVE' && !selectedDate
                  ? 'bg-rose-600 text-white font-bold animate-pulse'
                  : 'bg-rose-950/80 text-rose-300 hover:bg-rose-900 border border-rose-800/70'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-rose-400 animate-ping inline-block" />
              <span>Live ({liveMatches.length})</span>
            </button>

            <button
              onClick={() => handleSelectDay('2026-10-01')}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                selectedDate === '2026-10-01'
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
              }`}
            >
              Yesterday (Oct 1)
            </button>

            <button
              onClick={() => handleSelectDay('2026-10-02')}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                selectedDate === '2026-10-02'
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
              }`}
            >
              Today (Oct 2)
            </button>

            <button
              onClick={() => handleSelectDay('2026-10-03')}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                selectedDate === '2026-10-03'
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
              }`}
            >
              Tomorrow (Oct 3)
            </button>

            <button
              onClick={() => {
                setSelectedStatus('SCHEDULED');
                setSelectedDate(undefined);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                selectedStatus === 'SCHEDULED' && !selectedDate
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
              }`}
            >
              All Upcoming
            </button>
          </div>

          {/* Timezone & Reset */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs font-mono bg-slate-900 px-2 py-1 rounded-lg border border-slate-800">
              <span className="text-slate-400">TZ:</span>
              <button
                onClick={() => setTimeZone('UTC')}
                className={`px-1.5 py-0.5 rounded ${timeZone === 'UTC' ? 'bg-slate-800 text-emerald-400 font-bold' : 'text-slate-400'}`}
              >
                UTC
              </button>
              <button
                onClick={() => setTimeZone('local')}
                className={`px-1.5 py-0.5 rounded ${timeZone === 'local' ? 'bg-slate-800 text-emerald-400 font-bold' : 'text-slate-400'}`}
              >
                Local
              </button>
            </div>

            <button
              onClick={handleResetFilters}
              className="inline-flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors px-2 py-1"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reset</span>
            </button>
          </div>
        </div>

        {/* Search & Competition Filter */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="relative sm:col-span-2">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search team or fixture..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/60 font-sans"
            />
          </div>

          <div>
            <select
              value={selectedLeague || ''}
              onChange={(e) => setSelectedLeague(e.target.value || undefined)}
              className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 font-sans"
            >
              <option value="">All Competitions</option>
              {availableLeagueCodes.map((lg) => (
                <option key={lg} value={lg}>
                  {lg.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 3. Real-Time Live In-Play Matches Banner (Whenever live games exist) */}
      {liveMatches.length > 0 && selectedStatus !== 'LIVE' && (
        <div className="rounded-2xl border border-rose-900/60 bg-gradient-to-r from-rose-950/40 via-surface-card to-slate-900/80 p-4 space-y-3 shadow-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping inline-block" />
              <h2 className="text-sm font-bold text-rose-300 font-mono uppercase tracking-wider flex items-center gap-1.5">
                <span>Live Matches In-Play Now</span>
                <span className="px-2 py-0.5 rounded-full bg-rose-900/80 text-white text-[11px]">
                  {liveMatches.length}
                </span>
              </h2>
            </div>
            <button
              onClick={handleSelectLive}
              className="text-xs font-mono text-rose-300 hover:text-white font-semibold flex items-center gap-1"
            >
              <span>View All Live</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="divide-y divide-rose-950/60 rounded-xl overflow-hidden border border-rose-900/40 bg-surface-card">
            {liveMatches.slice(0, 4).map((m) => (
              <MatchRow key={m.id} match={m} timeZone={timeZone} />
            ))}
          </div>
        </div>
      )}

      {/* 4. FotMob Hierarchical League-Grouped Fixture Cards */}
      <div className="space-y-4">
        {matchesLoading ? (
          <div className="rounded-2xl border border-surface-border bg-surface-card p-12 text-center">
            <LoadingSpinner label="Fetching canonical fixtures..." />
          </div>
        ) : matchesError ? (
          <ErrorCard error={matchesError as Error} title="Unable to Load Matches" onRetry={() => refetchMatches()} />
        ) : homepageMatches.length === 0 ? (
          <div className="rounded-2xl border border-surface-border bg-surface-card p-12 text-center space-y-2">
            <Clock className="w-8 h-8 text-slate-500 mx-auto" />
            <h3 className="font-semibold text-sm text-slate-200">No Matches Found for this Filter</h3>
            <p className="text-xs text-slate-400 font-sans max-w-sm mx-auto">
              No fixtures currently match the chosen date or competition. Try clicking "Today", "Live", or resetting filters.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {Object.entries(leagueGroups).map(([leagueKey, matchesInLeague]) => {
              const lMeta = getLeagueMeta(leagueKey);

              return (
                <div
                  key={leagueKey}
                  className="rounded-2xl border border-surface-border bg-surface-card overflow-hidden shadow-sm"
                >
                  {/* FotMob League Header Banner */}
                  <div className="px-4 py-2.5 bg-slate-900/90 border-b border-surface-border flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="text-lg select-none">{lMeta.flag}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs sm:text-sm font-bold text-white tracking-wide font-sans">
                          {lMeta.name}
                        </span>
                        <span className="text-[11px] text-slate-400 font-mono">
                          • {lMeta.country}
                        </span>
                      </div>
                    </div>

                    <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded-md border border-slate-800">
                      {matchesInLeague.length} {matchesInLeague.length === 1 ? 'match' : 'matches'}
                    </span>
                  </div>

                  {/* League Match Rows */}
                  <div className="divide-y divide-surface-border">
                    {matchesInLeague.map((m) => (
                      <MatchRow key={m.id} match={m} timeZone={timeZone} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 5. Competitions Overview Grid */}
      <section className="space-y-4 pt-4 border-t border-surface-border/70">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Supported Competitions Overview</span>
          </h2>
          <span className="text-xs font-mono text-slate-400">8 Supported Competitions</span>
        </div>

        <CompetitionCards competitions={primaryCompetitions} />
      </section>

      {/* 6. Honest Zero-Data Current Season Notice */}
      <CurrentSeasonBanner
        currentSeason={acqStatus?.coverage?.current_season || '2026/27'}
        leaguesCoverage={competitionsMap}
      />
    </div>
  );
};
