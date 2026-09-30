import React, { useState } from 'react';
import { Database, ChevronLeft, ChevronRight, AlertCircle, RefreshCw } from 'lucide-react';
import { useMatches, useLeagues } from '../api/queries';
import { MatchRow } from '../components/matches/MatchRow';
import { MatchFilters, MatchFiltersState } from '../components/matches/MatchFilters';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

export const MatchExplorerPage: React.FC = () => {
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;
  const [filters, setFilters] = useState<MatchFiltersState>({});

  const { data: leaguesData } = useLeagues();
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

  const { data, isLoading, error, refetch, isFetching } = useMatches({
    page,
    page_size: pageSize,
    league: filters.league,
    status: filters.status,
    date: filters.date,
    team: filters.team,
  });

  const matches = data?.data || [];
  const meta = data?.meta || { page: 1, page_size: pageSize, total: 0 };
  const totalPages = Math.max(1, Math.ceil(meta.total / pageSize));

  const handleFilterChange = (newFilters: MatchFiltersState) => {
    setFilters(newFilters);
    setPage(1); // Reset to page 1 on filter change
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Database className="w-6 h-6 text-emerald-400" />
            <span>Match Explorer</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Browse and search canonical fixtures across European competitions with pre-match audit statuses.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-400">
            {meta.total} matches recorded
          </span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            title="Refresh Fixture List"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter Component */}
      <MatchFilters
        filters={filters}
        onFilterChange={handleFilterChange}
        availableLeagues={availableLeagueCodes}
      />

      {/* Fixtures List */}
      <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden shadow-sm">
        {isLoading ? (
          <LoadingSpinner label="Fetching fixtures from canonical store..." />
        ) : error ? (
          <div className="p-6">
            <ErrorCard error={error as Error} title="Unable to Load Matches" onRetry={() => refetch()} />
          </div>
        ) : matches.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <AlertCircle className="w-8 h-8 text-slate-500 mx-auto" />
            <h3 className="font-semibold text-sm text-slate-200">No Matching Fixtures Found</h3>
            <p className="text-xs text-slate-400 font-sans max-w-sm mx-auto">
              No matches matched the current filter criteria. Try broadening your date or competition selection.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {matches.map((m) => (
              <MatchRow key={m.id} match={m} />
            ))}
          </div>
        )}

        {/* Pagination Bar */}
        {meta.total > 0 && (
          <div className="p-4 border-t border-surface-border bg-slate-950/60 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-mono">
            <span className="text-slate-400">
              Showing {(page - 1) * pageSize + 1} – {Math.min(page * pageSize, meta.total)} of{' '}
              {meta.total} fixtures
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || isLoading}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>

              <span className="px-3 py-1.5 rounded bg-slate-800 text-slate-200 font-bold">
                {page} / {totalPages}
              </span>

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || isLoading}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <span>Next</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
