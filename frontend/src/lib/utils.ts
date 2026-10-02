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
 * Converts a decimal probability (0..1) to standard European Decimal Odds (e.g. 0.50 -> 2.00)
 */
export function probabilityToDecimalOdds(prob?: number | null, decimals = 2): number | null {
  if (prob === null || prob === undefined || isNaN(prob) || prob <= 0) {
    return null;
  }
  return Number((1 / prob).toFixed(decimals));
}

/**
 * Formats decimal odds as European Odds string, e.g. "2.50"
 */
export function formatDecimalOdds(oddsOrProb?: number | null, isProb = false): string {
  if (oddsOrProb === null || oddsOrProb === undefined || isNaN(oddsOrProb) || oddsOrProb <= 0) {
    return '—';
  }
  const decimalOdds = isProb ? 1 / oddsOrProb : oddsOrProb;
  return decimalOdds.toFixed(2);
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
 * Formats a timestamp into date, time, and full string according to user's timezone preference
 */
export function formatDateTime(
  isoString?: string | null,
  timeZone: 'UTC' | 'local' | string = 'UTC'
): { date: string; time: string; full: string } {
  if (!isoString) return { date: '—', time: '—', full: '—' };
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) {
      return { date: isoString, time: '', full: isoString };
    }
    const tzOption = timeZone === 'local' ? undefined : timeZone;
    const date = d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      timeZone: tzOption,
    });
    const time = d.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: tzOption,
      hour12: false,
    });
    const tzLabel = timeZone === 'UTC' ? 'UTC' : (timeZone === 'local' ? 'Local' : timeZone);
    return { date, time: `${time} ${tzLabel}`, full: `${date} ${time} ${tzLabel}` };
  } catch {
    return { date: isoString, time: '', full: isoString };
  }
}

/**
 * Returns FotMob-style human-friendly date header for match lists:
 * "Today", "Tomorrow", "Yesterday", or formatted weekday e.g. "Saturday, Oct 3"
 */
export function getRelativeDateLabel(isoString?: string | null, timeZone: 'UTC' | 'local' | string = 'UTC'): string {
  if (!isoString) return 'Unscheduled';
  try {
    const matchDate = new Date(isoString);
    if (isNaN(matchDate.getTime())) return isoString;

    // Use current canonical system date (2026-10-02) as reference point
    const refDate = new Date();
    const tzOption = timeZone === 'local' ? undefined : timeZone;

    const matchDayStr = matchDate.toLocaleDateString('en-CA', { timeZone: tzOption }); // YYYY-MM-DD
    const todayStr = refDate.toLocaleDateString('en-CA', { timeZone: tzOption });

    const refTime = new Date(todayStr).getTime();
    const matchTime = new Date(matchDayStr).getTime();
    const diffDays = Math.round((matchTime - refTime) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    if (diffDays === -1) return 'Yesterday';

    return matchDate.toLocaleDateString(undefined, {
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
