import React from 'react';
import { Search, Filter, RotateCcw } from 'lucide-react';

export interface MatchFiltersState {
  league?: string;
  status?: string;
  date?: string;
  team?: string;
  sort_order?: 'asc' | 'desc';
}

export interface MatchFiltersProps {
  filters: MatchFiltersState;
  onFilterChange: (newFilters: MatchFiltersState) => void;
  availableLeagues?: string[];
  timeZone?: 'UTC' | 'local' | string;
  onTimeZoneChange?: (tz: 'UTC' | 'local') => void;
}

export const MatchFilters: React.FC<MatchFiltersProps> = ({
  filters,
  onFilterChange,
  availableLeagues = ['EPL', 'LA_LIGA', 'SERIE_A', 'BUNDESLIGA', 'LIGUE_1', 'UCL', 'NATIONS_LEAGUE', 'FRIENDLIES'],
  timeZone = 'UTC',
  onTimeZoneChange,
}) => {
  const handleChange = (key: keyof MatchFiltersState, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value || undefined,
    });
  };

  const handleReset = () => {
    onFilterChange({});
  };

  // Canonical date references: Today is 2026-10-02, Yesterday 2026-10-01, Tomorrow 2026-10-03
  const handleQuickDay = (dayStr: string) => {
    onFilterChange({
      ...filters,
      date: dayStr,
    });
  };

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3.5">
      {/* Top Filter Bar with Quick Day Chips and Timezone */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border/80">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-mono text-slate-400 font-semibold mr-1">Days:</span>
          <button
            onClick={() => handleQuickDay('2026-10-01')}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.date === '2026-10-01'
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Yesterday (Oct 1)
          </button>
          <button
            onClick={() => handleQuickDay('2026-10-02')}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.date === '2026-10-02'
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Today (Oct 2)
          </button>
          <button
            onClick={() => handleQuickDay('2026-10-03')}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.date === '2026-10-03'
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Tomorrow (Oct 3)
          </button>
          <button
            onClick={() => onFilterChange({ ...filters, status: 'SCHEDULED', date: undefined })}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.status === 'SCHEDULED' && !filters.date
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            All Upcoming
          </button>
        </div>

        {/* Timezone & Reset Controls */}
        <div className="flex items-center gap-2">
          {onTimeZoneChange && (
            <div className="flex items-center gap-1 text-xs font-mono bg-slate-900 px-2 py-1 rounded border border-slate-800">
              <span className="text-slate-400">Timezone:</span>
              <button
                onClick={() => onTimeZoneChange('UTC')}
                className={`px-1.5 py-0.5 rounded ${timeZone === 'UTC' ? 'bg-slate-800 text-emerald-400 font-bold' : 'text-slate-400'}`}
              >
                UTC
              </button>
              <button
                onClick={() => onTimeZoneChange('local')}
                className={`px-1.5 py-0.5 rounded ${timeZone === 'local' ? 'bg-slate-800 text-emerald-400 font-bold' : 'text-slate-400'}`}
              >
                Local
              </button>
            </div>
          )}

          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors px-2 py-1"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>
      </div>

      {/* Primary Filter Selectors & Sort */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Team Search */}
        <div className="relative">
          <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search team name..."
            value={filters.team || ''}
            onChange={(e) => handleChange('team', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          />
        </div>

        {/* Competition Dropdown */}
        <div>
          <select
            value={filters.league || ''}
            onChange={(e) => handleChange('league', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          >
            <option value="">All Competitions</option>
            {availableLeagues.map((lg) => (
              <option key={lg} value={lg}>
                {lg.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>

        {/* Status Dropdown */}
        <div>
          <select
            value={filters.status || ''}
            onChange={(e) => handleChange('status', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          >
            <option value="">All Statuses</option>
            <option value="FINISHED">Finished</option>
            <option value="SCHEDULED">Scheduled</option>
            <option value="PRE_MATCH">Pre-Match</option>
            <option value="LIVE">Live</option>
            <option value="POSTPONED">Postponed</option>
          </select>
        </div>

        {/* Specific Date input */}
        <div>
          <input
            type="date"
            value={filters.date || ''}
            onChange={(e) => handleChange('date', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans [color-scheme:dark]"
          />
        </div>

        {/* Sort Order Selector */}
        <div>
          <select
            value={filters.sort_order || 'asc'}
            onChange={(e) => handleChange('sort_order', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          >
            <option value="asc">Kickoff: Earliest First</option>
            <option value="desc">Kickoff: Latest First</option>
          </select>
        </div>
      </div>
    </div>
  );
};

