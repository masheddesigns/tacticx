import React, { useRef, useEffect, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Calendar, Radio, Sparkles, Clock } from 'lucide-react';
import { getTodayString, getDayOffsetString, formatDayDisplay } from '../../lib/utils';

export interface DateSliderTabsProps {
  selectedDate?: string; // YYYY-MM-DD
  onSelectDate: (date: string | undefined) => void;
  selectedStatus?: string;
  onSelectStatus?: (status: string | undefined) => void;
  timeZone?: 'IST' | 'UTC' | 'local' | string;
  onTimeZoneChange?: (tz: 'IST' | 'UTC') => void;
  liveCount?: number;
  minDate?: string;
  maxDate?: string;
}

export const DateSliderTabs: React.FC<DateSliderTabsProps> = ({
  selectedDate,
  onSelectDate,
  selectedStatus,
  onSelectStatus,
  timeZone = 'IST',
  onTimeZoneChange,
  liveCount = 0,
  minDate = '2026-10-01',
  maxDate = '2026-11-30',
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const activeTabRef = useRef<HTMLButtonElement>(null);

  const todayStr = useMemo(() => getTodayString(timeZone), [timeZone]);
  const yesterdayStr = useMemo(() => getDayOffsetString(-1, timeZone), [timeZone]);
  const tomorrowStr = useMemo(() => getDayOffsetString(1, timeZone), [timeZone]);

  // Generate a continuous sliding list of dates (-7 days before today to +14 days after today)
  const daysList = useMemo(() => {
    const list: Array<{
      dateStr: string;
      relativeLabel: string;
      dayMonthLabel: string;
      isToday: boolean;
      isYesterday: boolean;
      isTomorrow: boolean;
    }> = [];

    // Ensure range spans at least -7 to +14 days
    const startOffset = -7;
    const endOffset = 14;

    for (let offset = startOffset; offset <= endOffset; offset++) {
      const dateStr = getDayOffsetString(offset, timeZone);
      const isToday = dateStr === todayStr;
      const isYesterday = dateStr === yesterdayStr;
      const isTomorrow = dateStr === tomorrowStr;

      // Extract day and month in target timezone
      const parts = dateStr.split('-').map(Number);
      const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2], 12, 0, 0));
      const dayNum = d.getUTCDate();
      const monthShort = d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' }).toUpperCase();
      const weekdayShort = d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' }).toUpperCase();

      let relativeLabel = weekdayShort;
      if (isToday) relativeLabel = 'TODAY';
      else if (isYesterday) relativeLabel = 'YESTERDAY';
      else if (isTomorrow) relativeLabel = 'TOMORROW';

      list.push({
        dateStr,
        relativeLabel,
        dayMonthLabel: `${dayNum} ${monthShort}`,
        isToday,
        isYesterday,
        isTomorrow,
      });
    }

    // If selectedDate is outside the default window, prepend or append it
    if (selectedDate && !list.some((item) => item.dateStr === selectedDate)) {
      const parts = selectedDate.split('-').map(Number);
      const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2], 12, 0, 0));
      const dayNum = d.getUTCDate();
      const monthShort = d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' }).toUpperCase();
      const weekdayShort = d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' }).toUpperCase();
      
      const customItem = {
        dateStr: selectedDate,
        relativeLabel: weekdayShort,
        dayMonthLabel: `${dayNum} ${monthShort}`,
        isToday: selectedDate === todayStr,
        isYesterday: selectedDate === yesterdayStr,
        isTomorrow: selectedDate === tomorrowStr,
      };

      if (selectedDate < list[0].dateStr) {
        list.unshift(customItem);
      } else {
        list.push(customItem);
      }
    }

    return list;
  }, [timeZone, todayStr, yesterdayStr, tomorrowStr, selectedDate]);

  // Center selected active tab in the sliding strip
  useEffect(() => {
    if (activeTabRef.current && scrollContainerRef.current) {
      activeTabRef.current.scrollIntoView({
        behavior: 'smooth',
        inline: 'center',
        block: 'nearest',
      });
    }
  }, [selectedDate, selectedStatus]);

  const handleScroll = (direction: 'left' | 'right') => {
    if (scrollContainerRef.current) {
      const scrollAmount = direction === 'left' ? -260 : 260;
      scrollContainerRef.current.scrollBy({ left: scrollAmount, behavior: 'smooth' });
    }
  };

  const handleSelectDay = (dateStr: string) => {
    if (onSelectStatus && selectedStatus) {
      onSelectStatus(undefined);
    }
    onSelectDate(dateStr);
  };

  const handleSelectLive = () => {
    if (onSelectStatus) {
      onSelectStatus('LIVE');
    }
    onSelectDate(undefined);
  };

  const handleSelectAllUpcoming = () => {
    if (onSelectStatus) {
      onSelectStatus('SCHEDULED');
    }
    onSelectDate(undefined);
  };

  return (
    <div className="w-full bg-[#11141c] border border-[#202636] rounded-2xl p-2.5 sm:p-3 space-y-2.5 shadow-lg">
      {/* Top Utility Bar: Live Now, All Upcoming, Timezone, and Quick Jump */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-1.5">
          {/* Live Matches Shortcut */}
          <button
            onClick={handleSelectLive}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-sans font-semibold transition-all ${
              selectedStatus === 'LIVE' && !selectedDate
                ? 'bg-rose-500 text-white shadow-md shadow-rose-500/25 ring-1 ring-rose-400 font-bold'
                : 'bg-[#181d28] text-rose-300 hover:bg-[#202738] border border-rose-900/50'
            }`}
            title="Show only matches currently in-play"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
            </span>
            <span>Live Feed</span>
            {liveCount > 0 && (
              <span className="ml-0.5 px-1.5 py-0.2 bg-rose-950 text-rose-300 rounded-full text-[10px] font-mono border border-rose-800">
                {liveCount}
              </span>
            )}
          </button>

          {/* All Upcoming */}
          <button
            onClick={handleSelectAllUpcoming}
            className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-sans font-medium transition-all ${
              selectedStatus === 'SCHEDULED' && !selectedDate
                ? 'bg-[#21e786] text-[#0a0d14] font-bold shadow-md shadow-[#21e786]/20'
                : 'bg-[#181d28] text-slate-300 hover:text-white hover:bg-[#202738] border border-[#262e40]'
            }`}
          >
            <Radio className="w-3 h-3 text-[#21e786]" />
            <span>All Upcoming</span>
          </button>
        </div>

        {/* Right side: Timezone Badge & Today Jump */}
        <div className="flex items-center gap-1.5">
          {/* Quick Return to Today if currently browsing other days */}
          {selectedDate && selectedDate !== todayStr && (
            <button
              onClick={() => handleSelectDay(todayStr)}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs font-sans font-semibold bg-[#21e786]/10 text-[#21e786] hover:bg-[#21e786]/20 border border-[#21e786]/30 transition-all"
              title="Jump directly to today's matchday"
            >
              <Sparkles className="w-3 h-3" />
              <span>Jump to Today</span>
            </button>
          )}

          {/* Direct Calendar Date Input */}
          <div className="relative inline-flex items-center gap-1 px-2 py-1.5 rounded-xl text-xs font-sans font-medium bg-[#181d28] hover:bg-[#202738] border border-[#262e40] transition-colors cursor-pointer" title="Pick any matchday date">
            <Calendar className="w-3.5 h-3.5 text-[#21e786] pointer-events-none" />
            <input
              type="date"
              value={selectedDate || ''}
              min={minDate}
              max={maxDate}
              onChange={(e) => {
                if (e.target.value) {
                  handleSelectDay(e.target.value);
                }
              }}
              className="bg-transparent text-slate-200 text-xs focus:outline-none cursor-pointer [color-scheme:dark] w-24 sm:w-28 font-mono"
              title="Select custom matchday"
            />
          </div>

          {/* Timezone Indicator */}
          <div className="flex items-center gap-1 text-[11px] font-mono bg-[#141822] px-2.5 py-1.5 rounded-xl border border-[#262e40]">
            <Clock className="w-3 h-3 text-[#21e786]" />
            <span className="text-slate-400">TZ:</span>
            <button
              onClick={() => onTimeZoneChange && onTimeZoneChange(timeZone === 'IST' ? 'UTC' : 'IST')}
              className="text-[#21e786] font-bold hover:underline"
              title="Click to toggle timezone"
            >
              {timeZone}
            </button>
          </div>
        </div>
      </div>

      {/* FotMob Horizontal Sliding Tabs Strip */}
      <div className="relative flex items-center group">
        {/* Left Scroll Chevron */}
        <button
          onClick={() => handleScroll('left')}
          aria-label="Scroll dates backward"
          className="absolute -left-1 z-10 p-1.5 rounded-full bg-[#181d28]/95 hover:bg-[#22293a] text-slate-300 hover:text-white border border-[#2b3448] shadow-lg backdrop-blur-sm transition-all opacity-80 group-hover:opacity-100 hidden sm:flex items-center justify-center"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {/* Scrollable Date Track */}
        <div
          ref={scrollContainerRef}
          className="flex items-center gap-1.5 overflow-x-auto scroll-smooth scrollbar-none py-1 px-1 sm:px-6 w-full no-scrollbar select-none"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {daysList.map((item) => {
            const isSelected = selectedDate === item.dateStr && selectedStatus !== 'LIVE';

            return (
              <button
                key={item.dateStr}
                ref={isSelected ? activeTabRef : undefined}
                onClick={() => handleSelectDay(item.dateStr)}
                className={`flex-shrink-0 flex flex-col items-center justify-center min-w-[62px] sm:min-w-[68px] h-[52px] sm:h-[56px] px-2 rounded-xl transition-all duration-150 ${
                  isSelected
                    ? 'bg-[#21e786] text-[#0a0d14] font-bold shadow-md shadow-[#21e786]/25 ring-1 ring-[#21e786] scale-[1.02]'
                    : item.isToday
                    ? 'bg-[#181d28] text-white hover:bg-[#202738] border border-[#21e786]/50'
                    : 'bg-[#141720] text-slate-300 hover:text-white hover:bg-[#1c2230] border border-[#222838]'
                }`}
              >
                {/* Top line: Relative / Weekday Label */}
                <div className="flex items-center gap-1">
                  {item.isToday && !isSelected && (
                    <span className="w-1.5 h-1.5 rounded-full bg-[#21e786] inline-block animate-pulse" />
                  )}
                  <span
                    className={`text-[10px] tracking-wider font-semibold uppercase ${
                      isSelected
                        ? 'text-[#0a0d14] font-black'
                        : item.isToday
                        ? 'text-[#21e786] font-bold'
                        : 'text-slate-400'
                    }`}
                  >
                    {item.relativeLabel}
                  </span>
                </div>

                {/* Bottom line: Day Number and Month */}
                <span
                  className={`text-xs sm:text-[13px] font-sans font-bold leading-tight mt-0.5 ${
                    isSelected ? 'text-[#0a0d14]' : 'text-slate-200'
                  }`}
                >
                  {item.dayMonthLabel}
                </span>
              </button>
            );
          })}
        </div>

        {/* Right Scroll Chevron */}
        <button
          onClick={() => handleScroll('right')}
          aria-label="Scroll dates forward"
          className="absolute -right-1 z-10 p-1.5 rounded-full bg-[#181d28]/95 hover:bg-[#22293a] text-slate-300 hover:text-white border border-[#2b3448] shadow-lg backdrop-blur-sm transition-all opacity-80 group-hover:opacity-100 hidden sm:flex items-center justify-center"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
