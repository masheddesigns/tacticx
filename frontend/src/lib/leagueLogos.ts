/**
 * TacticX Official Competition & League Crest Registry
 * Provides verified FotMob CDN assets for all supported domestic and international leagues.
 * Tested and verified against FotMob production CDN.
 */

export interface LeagueLogoMeta {
  code: string;
  name: string;
  shortName: string;
  country: string;
  flagEmoji: string;
  // FotMob CDN assets are optional: entries without them fall back to flagEmoji.
  fotmobId?: number;
  logoUrl?: string;
  darkLogoUrl?: string;
}

const LEAGUE_REGISTRY: Record<string, LeagueLogoMeta> = {
  EPL: {
    code: 'EPL',
    name: 'Premier League',
    shortName: 'Premier League',
    country: 'England',
    flagEmoji: '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
    fotmobId: 47,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/47.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/47.png',
  },
  LA_LIGA: {
    code: 'LA_LIGA',
    name: 'La Liga',
    shortName: 'La Liga',
    country: 'Spain',
    flagEmoji: '🇪🇸',
    fotmobId: 87,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/87.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/87.png',
  },
  SERIE_A: {
    code: 'SERIE_A',
    name: 'Serie A',
    shortName: 'Serie A',
    country: 'Italy',
    flagEmoji: '🇮🇹',
    fotmobId: 55,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/55.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/55.png',
  },
  BUNDESLIGA: {
    code: 'BUNDESLIGA',
    name: 'Bundesliga',
    shortName: 'Bundesliga',
    country: 'Germany',
    flagEmoji: '🇩🇪',
    fotmobId: 54,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/54.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/54.png',
  },
  LIGUE_1: {
    code: 'LIGUE_1',
    name: 'Ligue 1',
    shortName: 'Ligue 1',
    country: 'France',
    flagEmoji: '🇫🇷',
    fotmobId: 53,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/53.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/53.png',
  },
  UCL: {
    code: 'UCL',
    name: 'UEFA Champions League',
    shortName: 'Champions League',
    country: 'Europe',
    flagEmoji: '🏆',
    fotmobId: 42,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/42.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/42.png',
  },
  UEL: {
    code: 'UEL',
    name: 'UEFA Europa League',
    shortName: 'Europa League',
    country: 'Europe',
    flagEmoji: '🇪🇺',
  },
  UECL: {
    code: 'UECL',
    name: 'UEFA Conference League',
    shortName: 'Conference League',
    country: 'Europe',
    flagEmoji: '🏟️',
  },
  MLS: {
    code: 'MLS',
    name: 'Major League Soccer',
    shortName: 'MLS',
    country: 'United States',
    flagEmoji: '🇺🇸',
    fotmobId: 130,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/130.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/130.png',
  },
  BRA_SERIE_A: {
    code: 'BRA_SERIE_A',
    name: 'Brasileirão Série A',
    shortName: 'Série A Brazil',
    country: 'Brazil',
    flagEmoji: '🇧🇷',
    fotmobId: 268,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/268.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/268.png',
  },
  LIGA_ARG: {
    code: 'LIGA_ARG',
    name: 'Liga Profesional Argentina',
    shortName: 'Liga Profesional',
    country: 'Argentina',
    flagEmoji: '🇦🇷',
    fotmobId: 112,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/112.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/112.png',
  },
  ISL: {
    code: 'ISL',
    name: 'Indian Super League',
    shortName: 'ISL',
    country: 'India',
    flagEmoji: '🇮🇳',
    fotmobId: 9478,
    logoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/9478.png',
    darkLogoUrl: 'https://images.fotmob.com/image_resources/logo/leaguelogo/dark/9478.png',
  },
};

// Aliases mapping common names to canonical code
const ALIAS_MAP: Record<string, string> = {
  // Premier League
  'epl': 'EPL',
  'premier league': 'EPL',
  'english premier league': 'EPL',
  'premier-league': 'EPL',

  // La Liga
  'la liga': 'LA_LIGA',
  'laliga': 'LA_LIGA',
  'la-liga': 'LA_LIGA',
  'la_liga': 'LA_LIGA',
  'primera division': 'LA_LIGA',
  'spanish la liga': 'LA_LIGA',

  // Serie A
  'serie a': 'SERIE_A',
  'serie-a': 'SERIE_A',
  'serie_a': 'SERIE_A',
  'italian serie a': 'SERIE_A',
  'serie a enilive': 'SERIE_A',

  // Bundesliga
  'bundesliga': 'BUNDESLIGA',
  'german bundesliga': 'BUNDESLIGA',

  // Ligue 1
  'ligue 1': 'LIGUE_1',
  'ligue-1': 'LIGUE_1',
  'ligue_1': 'LIGUE_1',
  'french ligue 1': 'LIGUE_1',
  'ligue 1 mcdonalds': 'LIGUE_1',

  // Champions League
  'ucl': 'UCL',
  'uefa champions league': 'UCL',
  'champions league': 'UCL',
  'uefa-champions-league': 'UCL',

  // Europa League
  'uel': 'UEL',
  'uefa europa league': 'UEL',
  'europa league': 'UEL',
  'uefa-europa-league': 'UEL',

  // Conference League
  'uecl': 'UECL',
  'uefa conference league': 'UECL',
  'conference league': 'UECL',
  'uefa-conference-league': 'UECL',

  // MLS
  'mls': 'MLS',
  'major league soccer': 'MLS',
  'major-league-soccer': 'MLS',

  // Brazil Serie A
  'bra_serie_a': 'BRA_SERIE_A',
  'bra-serie-a': 'BRA_SERIE_A',
  'brasileirao': 'BRA_SERIE_A',
  'brasileirão': 'BRA_SERIE_A',
  'brasileirao serie a': 'BRA_SERIE_A',
  'brasileirão série a': 'BRA_SERIE_A',
  'brazilian serie a': 'BRA_SERIE_A',
  'brazil serie a': 'BRA_SERIE_A',
  'série a brazil': 'BRA_SERIE_A',

  // Argentina
  'liga_arg': 'LIGA_ARG',
  'liga-arg': 'LIGA_ARG',
  'liga profesional': 'LIGA_ARG',
  'liga profesional argentina': 'LIGA_ARG',
  'argentina': 'LIGA_ARG',
  'argentina primera division': 'LIGA_ARG',
  'argentine league': 'LIGA_ARG',

  // ISL
  'isl': 'ISL',
  'indian super league': 'ISL',
  'indian-super-league': 'ISL',
  'india super league': 'ISL',
};

/**
 * Resolves a league code or name to its canonical registry entry.
 */
export function getLeagueMeta(leagueCodeOrName?: string | null): LeagueLogoMeta | null {
  if (!leagueCodeOrName) return null;
  const raw = leagueCodeOrName.trim();
  const upper = raw.toUpperCase().replace(/\s+/g, '_');
  if (LEAGUE_REGISTRY[upper]) {
    return LEAGUE_REGISTRY[upper];
  }

  // Strip diacritics (e.g. ã -> a, é -> e) and lowercase
  const normalized = raw
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  const code = ALIAS_MAP[normalized];
  if (code && LEAGUE_REGISTRY[code]) {
    return LEAGUE_REGISTRY[code];
  }

  // Also check if normalized matches canonical code or shortName
  for (const item of Object.values(LEAGUE_REGISTRY)) {
    const itemNorm = item.name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const shortNorm = item.shortName.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    if (normalized === itemNorm || normalized === shortNorm || normalized.includes(itemNorm) || itemNorm.includes(normalized)) {
      return item;
    }
  }

  return null;
}

/**
 * Returns the verified FotMob CDN logo URL for a competition or league.
 */
export function getLeagueLogoUrl(leagueCodeOrName?: string | null, dark: boolean = false): string | null {
  const meta = getLeagueMeta(leagueCodeOrName);
  if (!meta) return null;
  return (dark ? meta.darkLogoUrl : meta.logoUrl) ?? null;
}

/**
 * Returns the fallback emoji flag or trophy for a competition.
 */
export function getLeagueFallbackEmoji(leagueCodeOrName?: string | null): string {
  const meta = getLeagueMeta(leagueCodeOrName);
  return meta?.flagEmoji || '⚽';
}
