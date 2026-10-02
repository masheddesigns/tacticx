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

export function formatDateTime(isoString?: string | null): { date: string; time: string; full: string } {
  if (!isoString) return { date: '—', time: '—', full: '—' };
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) {
      return { date: isoString, time: '', full: isoString };
    }
    const date = d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      timeZone: 'UTC',
    });
    const time = d.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
      hour12: false,
    });
    return { date, time: `${time} UTC`, full: `${date} ${time} UTC` };
  } catch {
    return { date: isoString, time: '', full: isoString };
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
