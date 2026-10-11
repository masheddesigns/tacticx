import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatProbability(value?: number | null, decimals = 1): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—';
  }
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Converts pure mathematical probability (0..1) to commercial bookmaker decimal odds
 * like Parimatch, Bet365, etc. by incorporating the standard 5-6% bookmaker margin (overround).
 * Pure odds: 1 / P.
 * Commercial odds: 1 / (P * (1 + margin)).
 */
export function probabilityToBookmakerOdds(
  prob?: number | null,
  marginPercent = 5.0,
  decimals = 2
): number | null {
  if (prob === null || prob === undefined || isNaN(prob) || prob <= 0 || prob >= 1) {
    return null;
  }
  // Margin multiplier (e.g. 5% overround = 1.05)
  const multiplier = 1 + marginPercent / 100;
  const commercialProb = Math.min(0.98, prob * multiplier);
  const rawOdds = 1 / commercialProb;
  return Number(rawOdds.toFixed(decimals));
}

/**
 * Converts a decimal probability (0..1) to standard European Decimal Odds (e.g. 0.50 -> 2.00)
 */
export function probabilityToDecimalOdds(prob?: number | null, decimals = 2, withBookmakerMargin = true): number | null {
  if (prob === null || prob === undefined || isNaN(prob) || prob <= 0) {
    return null;
  }
  if (withBookmakerMargin) {
    return probabilityToBookmakerOdds(prob, 5.0, decimals);
  }
  return Number((1 / prob).toFixed(decimals));
}

/**
 * Formats decimal odds as European Odds string, e.g. "2.15" (matching Parimatch slip style)
 */
export function formatDecimalOdds(oddsOrProb?: number | null, isProb = false, withMargin = true): string {
  if (oddsOrProb === null || oddsOrProb === undefined || isNaN(oddsOrProb) || oddsOrProb <= 0) {
    return '—';
  }
  if (isProb) {
    const odds = probabilityToDecimalOdds(oddsOrProb, 2, withMargin);
    return odds ? odds.toFixed(2) : '—';
  }
  return oddsOrProb.toFixed(2);
}

/**
 * Returns human-friendly payout explanation for a given decimal odds and stake
 */
export function getPayoutExplanation(odds: number, stake = 10, currency = '$'): string {
  const payout = (stake * odds).toFixed(2);
  const profit = (stake * odds - stake).toFixed(2);
  return `${currency}${stake} bet returns ${currency}${payout} (${currency}${profit} profit)`;
}

export function formatLambda(value?: number | null, decimals = 2): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—';
  }
  return value.toFixed(decimals);
}

/**
/**
 * Formats a timestamp into date, time, and full string according to user's timezone preference.
 * Defaults to IST (Indian Standard Time, Asia/Kolkata, UTC+5:30) matching FotMob India standard.
 */
export function formatDateTime(
  isoString?: string | null,
  timeZone: 'IST' | 'UTC' | 'local' | string = 'IST'
): { date: string; time: string; full: string } {
  if (!isoString) return { date: '—', time: '—', full: '—' };
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) {
      return { date: isoString, time: '', full: isoString };
    }
    const tzOption = timeZone === 'IST' ? 'Asia/Kolkata' : (timeZone === 'local' ? undefined : (timeZone === 'UTC' ? 'UTC' : timeZone));
    const date = d.toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      timeZone: tzOption,
    });
    const time = d.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: tzOption,
      hour12: false,
    });
    const tzLabel = timeZone === 'IST' ? 'IST' : (timeZone === 'UTC' ? 'UTC' : (timeZone === 'local' ? 'Local' : timeZone));
    return { date, time: `${time} ${tzLabel}`, full: `${date} ${time} ${tzLabel}` };
  } catch {
    return { date: isoString, time: '', full: isoString };
  }
}

/**
 * Returns formatted YYYY-MM-DD date string for today based on client or timezone (default IST)
 */
export function getTodayString(timeZone: 'IST' | 'UTC' | 'local' | string = 'IST'): string {
  const d = new Date();
  const tzOption = timeZone === 'IST' ? 'Asia/Kolkata' : (timeZone === 'local' ? undefined : (timeZone === 'UTC' ? 'UTC' : timeZone));
  return d.toLocaleDateString('en-CA', { timeZone: tzOption }); // returns YYYY-MM-DD
}

/**
 * Returns formatted YYYY-MM-DD string offset by a number of days (+1 tomorrow, -1 yesterday) in target TZ
 */
export function getDayOffsetString(offsetDays: number, timeZone: 'IST' | 'UTC' | 'local' | string = 'IST'): string {
  const tzOption = timeZone === 'IST' ? 'Asia/Kolkata' : (timeZone === 'local' ? undefined : (timeZone === 'UTC' ? 'UTC' : timeZone));
  const now = new Date();
  const todayStr = now.toLocaleDateString('en-CA', { timeZone: tzOption });
  const [y, m, day] = todayStr.split('-').map(Number);
  const target = new Date(Date.UTC(y, m - 1, day + offsetDays, 12, 0, 0));
  return target.toLocaleDateString('en-CA', { timeZone: 'UTC' });
}

/**
 * Formats a YYYY-MM-DD string into a short label like "11 Oct"
 */
export function formatDayDisplay(dateStr: string, timeZone: 'IST' | 'UTC' | 'local' | string = 'IST'): string {
  try {
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      const d = new Date(Date.UTC(year, month, day, 12, 0, 0));
      return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric', timeZone: 'UTC' });
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

/**
 * Returns FotMob-style human-friendly date header for match lists:
 * "Today", "Tomorrow", "Yesterday", or formatted weekday e.g. "Sunday, 11 Oct" in IST
 */
export function getRelativeDateLabel(isoString?: string | null, timeZone: 'IST' | 'UTC' | 'local' | string = 'IST'): string {
  if (!isoString) return 'Unscheduled';
  try {
    const matchDate = new Date(isoString);
    if (isNaN(matchDate.getTime())) return isoString;

    const refDate = new Date();
    const tzOption = timeZone === 'IST' ? 'Asia/Kolkata' : (timeZone === 'local' ? undefined : (timeZone === 'UTC' ? 'UTC' : timeZone));

    const matchDayStr = matchDate.toLocaleDateString('en-CA', { timeZone: tzOption }); // YYYY-MM-DD
    const todayStr = refDate.toLocaleDateString('en-CA', { timeZone: tzOption });

    const refParts = todayStr.split('-').map(Number);
    const matchParts = matchDayStr.split('-').map(Number);
    const refUtc = Date.UTC(refParts[0], refParts[1] - 1, refParts[2]);
    const matchUtc = Date.UTC(matchParts[0], matchParts[1] - 1, matchParts[2]);
    const diffDays = Math.round((matchUtc - refUtc) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    if (diffDays === -1) return 'Yesterday';

    return matchDate.toLocaleDateString('en-GB', {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
      timeZone: tzOption,
    });
  } catch {
    return 'Upcoming';
  }
}

export function copyToClipboard(text: string): Promise<boolean> {
  if (navigator?.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => true).catch(() => false);
  }
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    return Promise.resolve(true);
  } catch {
    return Promise.resolve(false);
  }
}
