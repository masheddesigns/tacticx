/**
 * Team Logo & Metadata Resolver
 * Provides official high-resolution crest URLs and FotMob-grade team styling across:
 * - Premier League (EPL)
 * - La Liga (Spain)
 * - Serie A (Italy)
 * - Bundesliga (Germany)
 * - Ligue 1 (France)
 * - Indian Super League (ISL)
 * - Major League Soccer (MLS)
 * - Brasileirão Série A (Brazil)
 * - Liga Profesional Argentina
 * - UEFA Champions League / European Giants
 * - International Teams
 */

export interface TeamLogoMeta {
  name: string;
  shortName: string;
  logoUrl?: string;
  primaryColor: string;
  secondaryColor?: string;
  initials: string;
}

const FOTMOB_BASE = 'https://images.fotmob.com/image_resources/logo/teamlogo';
const APISPORTS_BASE = 'https://media.api-sports.io/football/teams';

// Comprehensive registry of official club crests
const TEAM_REGISTRY: Record<string, TeamLogoMeta> = {
  // === PREMIER LEAGUE ===
  'arsenal': {
    name: 'Arsenal',
    shortName: 'ARS',
    logoUrl: `${FOTMOB_BASE}/9825.png`,
    primaryColor: '#EF0107',
    initials: 'ARS',
  },
  'manchester city': {
    name: 'Manchester City',
    shortName: 'MCI',
    logoUrl: `${FOTMOB_BASE}/8456.png`,
    primaryColor: '#6CABDD',
    initials: 'MCI',
  },
  'liverpool': {
    name: 'Liverpool',
    shortName: 'LIV',
    logoUrl: `${FOTMOB_BASE}/8650.png`,
    primaryColor: '#C8102E',
    initials: 'LIV',
  },
  'chelsea': {
    name: 'Chelsea',
    shortName: 'CHE',
    logoUrl: `${FOTMOB_BASE}/8455.png`,
    primaryColor: '#034694',
    initials: 'CHE',
  },
  'manchester united': {
    name: 'Manchester United',
    shortName: 'MUN',
    logoUrl: `${FOTMOB_BASE}/10260.png`,
    primaryColor: '#DA291C',
    initials: 'MUN',
  },
  'tottenham': {
    name: 'Tottenham',
    shortName: 'TOT',
    logoUrl: `${FOTMOB_BASE}/8586.png`,
    primaryColor: '#132257',
    initials: 'TOT',
  },
  'aston villa': {
    name: 'Aston Villa',
    shortName: 'AVL',
    logoUrl: `${FOTMOB_BASE}/10252.png`,
    primaryColor: '#95BFE5',
    initials: 'AVL',
  },
  'newcastle': {
    name: 'Newcastle',
    shortName: 'NEW',
    logoUrl: `${FOTMOB_BASE}/10261.png`,
    primaryColor: '#241F20',
    initials: 'NEW',
  },
  'west ham': {
    name: 'West Ham',
    shortName: 'WHU',
    logoUrl: `${FOTMOB_BASE}/8654.png`,
    primaryColor: '#7A263A',
    initials: 'WHU',
  },
  'brighton': {
    name: 'Brighton',
    shortName: 'BHA',
    logoUrl: `${FOTMOB_BASE}/10204.png`,
    primaryColor: '#0057B8',
    initials: 'BHA',
  },
  'wolves': {
    name: 'Wolves',
    shortName: 'WOL',
    logoUrl: `${FOTMOB_BASE}/8659.png`,
    primaryColor: '#FDB913',
    initials: 'WOL',
  },
  'crystal palace': {
    name: 'Crystal Palace',
    shortName: 'CRY',
    logoUrl: `${FOTMOB_BASE}/9826.png`,
    primaryColor: '#1B458F',
    initials: 'CRY',
  },
  'everton': {
    name: 'Everton',
    shortName: 'EVE',
    logoUrl: `${FOTMOB_BASE}/8668.png`,
    primaryColor: '#003399',
    initials: 'EVE',
  },
  'brentford': {
    name: 'Brentford',
    shortName: 'BRE',
    logoUrl: `${FOTMOB_BASE}/9937.png`,
    primaryColor: '#E30613',
    initials: 'BRE',
  },
  'fulham': {
    name: 'Fulham',
    shortName: 'FUL',
    logoUrl: `${FOTMOB_BASE}/9879.png`,
    primaryColor: '#CC0000',
    initials: 'FUL',
  },
  'bournemouth': {
    name: 'Bournemouth',
    shortName: 'BOU',
    logoUrl: `${FOTMOB_BASE}/8678.png`,
    primaryColor: '#DA291C',
    initials: 'BOU',
  },
  'nottingham forest': {
    name: 'Nottingham Forest',
    shortName: 'NFO',
    logoUrl: `${FOTMOB_BASE}/10203.png`,
    primaryColor: '#DD0000',
    initials: 'NFO',
  },
  'burnley': {
    name: 'Burnley',
    shortName: 'BUR',
    logoUrl: `${FOTMOB_BASE}/8191.png`,
    primaryColor: '#6C1D45',
    initials: 'BUR',
  },
  'sheffield united': {
    name: 'Sheffield United',
    shortName: 'SHU',
    logoUrl: `${FOTMOB_BASE}/8657.png`,
    primaryColor: '#EE2737',
    initials: 'SHU',
  },
  'luton': {
    name: 'Luton',
    shortName: 'LUT',
    logoUrl: `${FOTMOB_BASE}/8344.png`,
    primaryColor: '#F78F1E',
    initials: 'LUT',
  },
  'hull': {
    name: 'Hull',
    shortName: 'HUL',
    logoUrl: `${FOTMOB_BASE}/8669.png`,
    primaryColor: '#F5A623',
    initials: 'HUL',
  },

  // === LA LIGA ===
  'real madrid': {
    name: 'Real Madrid',
    shortName: 'RMA',
    logoUrl: `${FOTMOB_BASE}/8633.png`,
    primaryColor: '#FFFFFF',
    initials: 'RMA',
  },
  'barcelona': {
    name: 'Barcelona',
    shortName: 'FCB',
    logoUrl: `${FOTMOB_BASE}/8634.png`,
    primaryColor: '#004D98',
    initials: 'BAR',
  },
  'atletico madrid': {
    name: 'Atlético Madrid',
    shortName: 'ATM',
    logoUrl: `${FOTMOB_BASE}/9906.png`,
    primaryColor: '#CB3524',
    initials: 'ATM',
  },
  'athletic bilbao': {
    name: 'Athletic Club',
    shortName: 'ATH',
    logoUrl: `${FOTMOB_BASE}/8315.png`,
    primaryColor: '#EE2524',
    initials: 'ATH',
  },
  'real sociedad': {
    name: 'Real Sociedad',
    shortName: 'RSO',
    logoUrl: `${FOTMOB_BASE}/8560.png`,
    primaryColor: '#0067B1',
    initials: 'RSO',
  },
  'real betis': {
    name: 'Real Betis',
    shortName: 'BET',
    logoUrl: `${FOTMOB_BASE}/8603.png`,
    primaryColor: '#0BB364',
    initials: 'BET',
  },
  'villarreal': {
    name: 'Villarreal',
    shortName: 'VIL',
    logoUrl: `${FOTMOB_BASE}/10205.png`,
    primaryColor: '#FFE600',
    initials: 'VIL',
  },
  'valencia': {
    name: 'Valencia',
    shortName: 'VAL',
    logoUrl: `${FOTMOB_BASE}/10267.png`,
    primaryColor: '#FF6600',
    initials: 'VAL',
  },
  'sevilla': {
    name: 'Sevilla',
    shortName: 'SEV',
    logoUrl: `${FOTMOB_BASE}/8302.png`,
    primaryColor: '#D4001F',
    initials: 'SEV',
  },
  'girona': {
    name: 'Girona',
    shortName: 'GIR',
    logoUrl: `${FOTMOB_BASE}/9912.png`,
    primaryColor: '#CD1224',
    initials: 'GIR',
  },
  'celta': {
    name: 'Celta Vigo',
    shortName: 'CEL',
    logoUrl: `${FOTMOB_BASE}/9910.png`,
    primaryColor: '#8AC3EE',
    initials: 'CEL',
  },
  'osasuna': {
    name: 'Osasuna',
    shortName: 'OSA',
    logoUrl: `${FOTMOB_BASE}/8371.png`,
    primaryColor: '#D91A2A',
    initials: 'OSA',
  },
  'mallorca': {
    name: 'Mallorca',
    shortName: 'MLL',
    logoUrl: `${FOTMOB_BASE}/8401.png`,
    primaryColor: '#E20613',
    initials: 'MLL',
  },
  'getafe': {
    name: 'Getafe',
    shortName: 'GET',
    logoUrl: `${FOTMOB_BASE}/8305.png`,
    primaryColor: '#005CA9',
    initials: 'GET',
  },
  'rayo vallecano': {
    name: 'Rayo Vallecano',
    shortName: 'RAY',
    logoUrl: `${FOTMOB_BASE}/8370.png`,
    primaryColor: '#E51B24',
    initials: 'RAY',
  },
  'las palmas': {
    name: 'Las Palmas',
    shortName: 'LPA',
    logoUrl: `${FOTMOB_BASE}/8306.png`,
    primaryColor: '#FFD100',
    initials: 'LPA',
  },
  'alaves': {
    name: 'Alavés',
    shortName: 'ALA',
    logoUrl: `${FOTMOB_BASE}/9866.png`,
    primaryColor: '#005BA9',
    initials: 'ALA',
  },
  'cadiz': {
    name: 'Cádiz',
    shortName: 'CAD',
    logoUrl: `${FOTMOB_BASE}/8385.png`,
    primaryColor: '#FFD700',
    initials: 'CAD',
  },
  'granada': {
    name: 'Granada',
    shortName: 'GRA',
    logoUrl: `${FOTMOB_BASE}/9783.png`,
    primaryColor: '#A6192E',
    initials: 'GRA',
  },
  'almeria': {
    name: 'Almería',
    shortName: 'ALM',
    logoUrl: `${FOTMOB_BASE}/9865.png`,
    primaryColor: '#E41B13',
    initials: 'ALM',
  },
  'elche': {
    name: 'Elche',
    shortName: 'ELC',
    logoUrl: `${FOTMOB_BASE}/10268.png`,
    primaryColor: '#00843D',
    initials: 'ELC',
  },
  'deportivo la coruna': {
    name: 'Deportivo La Coruña',
    shortName: 'DEP',
    logoUrl: `${FOTMOB_BASE}/9784.png`,
    primaryColor: '#005BA9',
    initials: 'DEP',
  },

  // === SERIE A ===
  'inter': {
    name: 'Inter',
    shortName: 'INT',
    logoUrl: `${FOTMOB_BASE}/8636.png`,
    primaryColor: '#001EA0',
    initials: 'INT',
  },
  'milan': {
    name: 'Milan',
    shortName: 'MIL',
    logoUrl: `${FOTMOB_BASE}/8564.png`,
    primaryColor: '#FB090B',
    initials: 'MIL',
  },
  'juventus': {
    name: 'Juventus',
    shortName: 'JUV',
    logoUrl: `${FOTMOB_BASE}/9885.png`,
    primaryColor: '#000000',
    initials: 'JUV',
  },
  'napoli': {
    name: 'Napoli',
    shortName: 'NAP',
    logoUrl: `${FOTMOB_BASE}/9875.png`,
    primaryColor: '#008FD7',
    initials: 'NAP',
  },
  'roma': {
    name: 'Roma',
    shortName: 'ROM',
    logoUrl: `${FOTMOB_BASE}/8686.png`,
    primaryColor: '#8E1F2F',
    initials: 'ROM',
  },
  'lazio': {
    name: 'Lazio',
    shortName: 'LAZ',
    logoUrl: `${FOTMOB_BASE}/8543.png`,
    primaryColor: '#87D8F7',
    initials: 'LAZ',
  },
  'atalanta': {
    name: 'Atalanta',
    shortName: 'ATA',
    logoUrl: `${FOTMOB_BASE}/8524.png`,
    primaryColor: '#1E71B8',
    initials: 'ATA',
  },
  'fiorentina': {
    name: 'Fiorentina',
    shortName: 'FIO',
    logoUrl: `${FOTMOB_BASE}/8535.png`,
    primaryColor: '#4F2683',
    initials: 'FIO',
  },
  'bologna': {
    name: 'Bologna',
    shortName: 'BOL',
    logoUrl: `${FOTMOB_BASE}/9857.png`,
    primaryColor: '#1B2838',
    initials: 'BOL',
  },
  'torino': {
    name: 'Torino',
    shortName: 'TOR',
    logoUrl: `${FOTMOB_BASE}/9888.png`,
    primaryColor: '#8B0000',
    initials: 'TOR',
  },
  'monza': {
    name: 'Monza',
    shortName: 'MON',
    logoUrl: `${FOTMOB_BASE}/6504.png`,
    primaryColor: '#E20613',
    initials: 'MON',
  },
  'genoa': {
    name: 'Genoa',
    shortName: 'GEN',
    logoUrl: `${FOTMOB_BASE}/10233.png`,
    primaryColor: '#A0001E',
    initials: 'GEN',
  },
  'lecce': {
    name: 'Lecce',
    shortName: 'LEC',
    logoUrl: `${FOTMOB_BASE}/9889.png`,
    primaryColor: '#FFD700',
    initials: 'LEC',
  },
  'sassuolo': {
    name: 'Sassuolo',
    shortName: 'SAS',
    logoUrl: `${FOTMOB_BASE}/7943.png`,
    primaryColor: '#00A651',
    initials: 'SAS',
  },
  'udinese': {
    name: 'Udinese',
    shortName: 'UDI',
    logoUrl: `${FOTMOB_BASE}/8600.png`,
    primaryColor: '#000000',
    initials: 'UDI',
  },
  'cagliari': {
    name: 'Cagliari',
    shortName: 'CAG',
    logoUrl: `${FOTMOB_BASE}/8529.png`,
    primaryColor: '#002B49',
    initials: 'CAG',
  },
  'verona': {
    name: 'Verona',
    shortName: 'VER',
    logoUrl: `${FOTMOB_BASE}/9876.png`,
    primaryColor: '#002F6C',
    initials: 'VER',
  },
  'empoli': {
    name: 'Empoli',
    shortName: 'EMP',
    logoUrl: `${FOTMOB_BASE}/8534.png`,
    primaryColor: '#005BA9',
    initials: 'EMP',
  },
  'frosinone': {
    name: 'Frosinone',
    shortName: 'FRO',
    logoUrl: `${FOTMOB_BASE}/9891.png`,
    primaryColor: '#FFD100',
    initials: 'FRO',
  },
  'salernitana': {
    name: 'Salernitana',
    shortName: 'SAL',
    logoUrl: `${FOTMOB_BASE}/6480.png`,
    primaryColor: '#800020',
    initials: 'SAL',
  },
  'como': {
    name: 'Como',
    shortName: 'COM',
    logoUrl: `${FOTMOB_BASE}/9893.png`,
    primaryColor: '#003399',
    initials: 'COM',
  },

  // === BUNDESLIGA ===
  'bayern munich': {
    name: 'Bayern Munich',
    shortName: 'BAY',
    logoUrl: `${FOTMOB_BASE}/9823.png`,
    primaryColor: '#DC052D',
    initials: 'FCB',
  },
  'dortmund': {
    name: 'Borussia Dortmund',
    shortName: 'BVB',
    logoUrl: `${FOTMOB_BASE}/9789.png`,
    primaryColor: '#FDE100',
    initials: 'BVB',
  },
  'leverkusen': {
    name: 'Bayer Leverkusen',
    shortName: 'B04',
    logoUrl: `${FOTMOB_BASE}/8178.png`,
    primaryColor: '#E32221',
    initials: 'B04',
  },
  'rb leipzig': {
    name: 'RB Leipzig',
    shortName: 'RBL',
    logoUrl: `${FOTMOB_BASE}/178475.png`,
    primaryColor: '#DD0742',
    initials: 'RBL',
  },
  'stuttgart': {
    name: 'VfB Stuttgart',
    shortName: 'VFB',
    logoUrl: `${FOTMOB_BASE}/10269.png`,
    primaryColor: '#E32219',
    initials: 'VFB',
  },
  'eintracht frankfurt': {
    name: 'Eintracht Frankfurt',
    shortName: 'SGE',
    logoUrl: `${FOTMOB_BASE}/9810.png`,
    primaryColor: '#E1000F',
    initials: 'SGE',
  },
  'hoffenheim': {
    name: 'Hoffenheim',
    shortName: 'TSG',
    logoUrl: `${FOTMOB_BASE}/8226.png`,
    primaryColor: '#1C63B7',
    initials: 'TSG',
  },
  'freiburg': {
    name: 'SC Freiburg',
    shortName: 'SCF',
    logoUrl: `${FOTMOB_BASE}/8358.png`,
    primaryColor: '#000000',
    initials: 'SCF',
  },
  'werder bremen': {
    name: 'Werder Bremen',
    shortName: 'SVW',
    logoUrl: `${FOTMOB_BASE}/8697.png`,
    primaryColor: '#1B7B34',
    initials: 'SVW',
  },
  'augsburg': {
    name: 'FC Augsburg',
    shortName: 'FCA',
    logoUrl: `${FOTMOB_BASE}/8406.png`,
    primaryColor: '#BA3733',
    initials: 'FCA',
  },
  'wolfsburg': {
    name: 'VfL Wolfsburg',
    shortName: 'WOB',
    logoUrl: `${FOTMOB_BASE}/8721.png`,
    primaryColor: '#65B32E',
    initials: 'WOB',
  },
  'm\'gladbach': {
    name: "Borussia M'gladbach",
    shortName: 'BMG',
    logoUrl: `${FOTMOB_BASE}/9788.png`,
    primaryColor: '#000000',
    initials: 'BMG',
  },
  'union berlin': {
    name: 'Union Berlin',
    shortName: 'FCU',
    logoUrl: `${FOTMOB_BASE}/8407.png`,
    primaryColor: '#EB1923',
    initials: 'FCU',
  },
  'bochum': {
    name: 'VfL Bochum',
    shortName: 'BOC',
    logoUrl: `${FOTMOB_BASE}/9911.png`,
    primaryColor: '#005CA9',
    initials: 'BOC',
  },
  'mainz': {
    name: 'Mainz 05',
    shortName: 'M05',
    logoUrl: `${FOTMOB_BASE}/9905.png`,
    primaryColor: '#C4122D',
    initials: 'M05',
  },
  'fc koln': {
    name: '1. FC Köln',
    shortName: 'KOE',
    logoUrl: `${FOTMOB_BASE}/8722.png`,
    primaryColor: '#ED1C24',
    initials: 'KOE',
  },
  'darmstadt': {
    name: 'SV Darmstadt 98',
    shortName: 'D98',
    logoUrl: `${FOTMOB_BASE}/8295.png`,
    primaryColor: '#004E9E',
    initials: 'D98',
  },
  'schalke 04': {
    name: 'Schalke 04',
    shortName: 'S04',
    logoUrl: `${FOTMOB_BASE}/9863.png`,
    primaryColor: '#004D9D',
    initials: 'S04',
  },

  // === LIGUE 1 ===
  'paris sg': {
    name: 'Paris Saint-Germain',
    shortName: 'PSG',
    logoUrl: `${FOTMOB_BASE}/9847.png`,
    primaryColor: '#004170',
    initials: 'PSG',
  },
  'monaco': {
    name: 'AS Monaco',
    shortName: 'ASM',
    logoUrl: `${FOTMOB_BASE}/9829.png`,
    primaryColor: '#E20613',
    initials: 'ASM',
  },
  'lille': {
    name: 'LOSC Lille',
    shortName: 'LOSC',
    logoUrl: `${FOTMOB_BASE}/8639.png`,
    primaryColor: '#E01E13',
    initials: 'LIL',
  },
  'nice': {
    name: 'OGC Nice',
    shortName: 'OGCN',
    logoUrl: `${FOTMOB_BASE}/9831.png`,
    primaryColor: '#D6001C',
    initials: 'NIC',
  },
  'lens': {
    name: 'RC Lens',
    shortName: 'RCL',
    logoUrl: `${FOTMOB_BASE}/8588.png`,
    primaryColor: '#ED1C24',
    initials: 'RCL',
  },
  'marseille': {
    name: 'Marseille',
    shortName: 'OM',
    logoUrl: `${FOTMOB_BASE}/8592.png`,
    primaryColor: '#00A3E0',
    initials: 'OM',
  },
  'lyon': {
    name: 'Lyon',
    shortName: 'OL',
    logoUrl: `${FOTMOB_BASE}/9748.png`,
    primaryColor: '#1D428A',
    initials: 'OL',
  },
  'rennes': {
    name: 'Rennes',
    shortName: 'SRFC',
    logoUrl: `${FOTMOB_BASE}/9851.png`,
    primaryColor: '#E20613',
    initials: 'REN',
  },
  'reims': {
    name: 'Stade de Reims',
    shortName: 'SDR',
    logoUrl: `${FOTMOB_BASE}/9837.png`,
    primaryColor: '#E20613',
    initials: 'REI',
  },
  'toulouse': {
    name: 'Toulouse',
    shortName: 'TFC',
    logoUrl: `${FOTMOB_BASE}/9941.png`,
    primaryColor: '#582C83',
    initials: 'TLS',
  },
  'montpellier': {
    name: 'Montpellier',
    shortName: 'MHSC',
    logoUrl: `${FOTMOB_BASE}/10249.png`,
    primaryColor: '#002B49',
    initials: 'MON',
  },
  'strasbourg': {
    name: 'Strasbourg',
    shortName: 'RCSA',
    logoUrl: `${FOTMOB_BASE}/9848.png`,
    primaryColor: '#005BA9',
    initials: 'STR',
  },
  'brest': {
    name: 'Stade Brestois',
    shortName: 'SB29',
    logoUrl: `${FOTMOB_BASE}/8521.png`,
    primaryColor: '#E20613',
    initials: 'BRE',
  },
  'nantes': {
    name: 'FC Nantes',
    shortName: 'FCN',
    logoUrl: `${FOTMOB_BASE}/9830.png`,
    primaryColor: '#FFDF00',
    initials: 'NAN',
  },
  'le havre': {
    name: 'Le Havre',
    shortName: 'HAC',
    logoUrl: `${FOTMOB_BASE}/9747.png`,
    primaryColor: '#72B6E6',
    initials: 'HAC',
  },
  'lorient': {
    name: 'FC Lorient',
    shortName: 'FCL',
    logoUrl: `${FOTMOB_BASE}/8689.png`,
    primaryColor: '#F36F21',
    initials: 'LOR',
  },
  'clermont': {
    name: 'Clermont Foot',
    shortName: 'CF63',
    logoUrl: `${FOTMOB_BASE}/9746.png`,
    primaryColor: '#8E1F2F',
    initials: 'CLE',
  },
  'metz': {
    name: 'FC Metz',
    shortName: 'FCM',
    logoUrl: `${FOTMOB_BASE}/8587.png`,
    primaryColor: '#800020',
    initials: 'MET',
  },
  'auxerre': {
    name: 'AJ Auxerre',
    shortName: 'AJA',
    logoUrl: `${FOTMOB_BASE}/8585.png`,
    primaryColor: '#004EA2',
    initials: 'AUX',
  },
  'angers': {
    name: 'Angers SCO',
    shortName: 'SCO',
    logoUrl: `${FOTMOB_BASE}/8682.png`,
    primaryColor: '#000000',
    initials: 'ANG',
  },

  // === INDIAN SUPER LEAGUE (ISL) ===
  'kerala blasters fc': {
    name: 'Kerala Blasters FC',
    shortName: 'KBFC',
    logoUrl: `${APISPORTS_BASE}/3468.png`,
    primaryColor: '#FFE600',
    initials: 'KBFC',
  },
  'mumbai city fc': {
    name: 'Mumbai City FC',
    shortName: 'MCFC',
    logoUrl: `${APISPORTS_BASE}/3469.png`,
    primaryColor: '#6CABDD',
    initials: 'MCFC',
  },
  'mohun bagan super giant': {
    name: 'Mohun Bagan Super Giant',
    shortName: 'MBSG',
    logoUrl: `${APISPORTS_BASE}/3467.png`,
    primaryColor: '#006A4E',
    initials: 'MBSG',
  },
  'east bengal fc': {
    name: 'East Bengal FC',
    shortName: 'EBFC',
    logoUrl: `${APISPORTS_BASE}/3472.png`,
    primaryColor: '#ED1C24',
    initials: 'EBFC',
  },
  'bengaluru fc': {
    name: 'Bengaluru FC',
    shortName: 'BFC',
    logoUrl: `${APISPORTS_BASE}/3466.png`,
    primaryColor: '#0054A6',
    initials: 'BFC',
  },
  'fc goa': {
    name: 'FC Goa',
    shortName: 'FCG',
    logoUrl: `${APISPORTS_BASE}/3470.png`,
    primaryColor: '#FF671F',
    initials: 'FCG',
  },
  'chennaiyin fc': {
    name: 'Chennaiyin FC',
    shortName: 'CFC',
    logoUrl: `${APISPORTS_BASE}/3471.png`,
    primaryColor: '#003399',
    initials: 'CFC',
  },
  'hyderabad fc': {
    name: 'Hyderabad FC',
    shortName: 'HFC',
    logoUrl: `${APISPORTS_BASE}/5526.png`,
    primaryColor: '#FFD700',
    initials: 'HFC',
  },
  'odisha fc': {
    name: 'Odisha FC',
    shortName: 'OFC',
    logoUrl: `${APISPORTS_BASE}/3473.png`,
    primaryColor: '#3B1865',
    initials: 'OFC',
  },
  'jamshedpur fc': {
    name: 'Jamshedpur FC',
    shortName: 'JFC',
    logoUrl: `${APISPORTS_BASE}/3475.png`,
    primaryColor: '#A0001E',
    initials: 'JFC',
  },
  'northeast united fc': {
    name: 'NorthEast United FC',
    shortName: 'NEUFC',
    logoUrl: `${APISPORTS_BASE}/3474.png`,
    primaryColor: '#D50000',
    initials: 'NEU',
  },
  'punjab fc': {
    name: 'Punjab FC',
    shortName: 'PFC',
    logoUrl: `${APISPORTS_BASE}/3476.png`,
    primaryColor: '#E65100',
    initials: 'PFC',
  },
  'mohammedan sc': {
    name: 'Mohammedan SC',
    shortName: 'MSC',
    logoUrl: `${APISPORTS_BASE}/10207.png`,
    primaryColor: '#000000',
    initials: 'MSC',
  },
  'churchill brothers sc': {
    name: 'Churchill Brothers SC',
    shortName: 'CB',
    logoUrl: `${APISPORTS_BASE}/3480.png`,
    primaryColor: '#D32F2F',
    initials: 'CB',
  },
  'inter kashi': {
    name: 'Inter Kashi',
    shortName: 'IK',
    logoUrl: `${APISPORTS_BASE}/21800.png`,
    primaryColor: '#1A237E',
    initials: 'IK',
  },

  // === MAJOR LEAGUE SOCCER (MLS) ===
  'inter miami cf': {
    name: 'Inter Miami CF',
    shortName: 'MIA',
    logoUrl: `${APISPORTS_BASE}/1603.png`,
    primaryColor: '#F7B5CD',
    initials: 'MIA',
  },
  'los angeles fc': {
    name: 'Los Angeles FC',
    shortName: 'LAFC',
    logoUrl: `${APISPORTS_BASE}/1608.png`,
    primaryColor: '#C39B54',
    initials: 'LAFC',
  },
  'la galaxy': {
    name: 'LA Galaxy',
    shortName: 'LAG',
    logoUrl: `${APISPORTS_BASE}/1609.png`,
    primaryColor: '#00245D',
    initials: 'LAG',
  },
  'seattle sounders': {
    name: 'Seattle Sounders',
    shortName: 'SEA',
    logoUrl: `${APISPORTS_BASE}/1595.png`,
    primaryColor: '#5D9741',
    initials: 'SEA',
  },
  'columbus crew': {
    name: 'Columbus Crew',
    shortName: 'CLB',
    logoUrl: `${APISPORTS_BASE}/1613.png`,
    primaryColor: '#FEF200',
    initials: 'CLB',
  },
  'atlanta united': {
    name: 'Atlanta United',
    shortName: 'ATL',
    logoUrl: `${APISPORTS_BASE}/1608.png`,
    primaryColor: '#80000A',
    initials: 'ATL',
  },
  'philadelphia union': {
    name: 'Philadelphia Union',
    shortName: 'PHI',
    logoUrl: `${APISPORTS_BASE}/1605.png`,
    primaryColor: '#041E42',
    initials: 'PHI',
  },
  'new york city fc': {
    name: 'New York City FC',
    shortName: 'NYC',
    logoUrl: `${APISPORTS_BASE}/1604.png`,
    primaryColor: '#6CACE4',
    initials: 'NYC',
  },
  'new york red bulls': {
    name: 'New York Red Bulls',
    shortName: 'RBNY',
    logoUrl: `${APISPORTS_BASE}/1600.png`,
    primaryColor: '#ED1E36',
    initials: 'NYRB',
  },
  'austin fc': {
    name: 'Austin FC',
    shortName: 'ATX',
    logoUrl: `${APISPORTS_BASE}/9568.png`,
    primaryColor: '#00B140',
    initials: 'ATX',
  },
  'nashville sc': {
    name: 'Nashville SC',
    shortName: 'NSH',
    logoUrl: `${APISPORTS_BASE}/1614.png`,
    primaryColor: '#ECE81A',
    initials: 'NSH',
  },
  'orlando city sc': {
    name: 'Orlando City SC',
    shortName: 'ORL',
    logoUrl: `${APISPORTS_BASE}/1598.png`,
    primaryColor: '#612B8C',
    initials: 'ORL',
  },
  'fc cincinnati': {
    name: 'FC Cincinnati',
    shortName: 'CIN',
    logoUrl: `${APISPORTS_BASE}/2242.png`,
    primaryColor: '#F05323',
    initials: 'CIN',
  },
  'portland timbers': {
    name: 'Portland Timbers',
    shortName: 'POR',
    logoUrl: `${APISPORTS_BASE}/1611.png`,
    primaryColor: '#004812',
    initials: 'POR',
  },
  'sporting kansas city': {
    name: 'Sporting Kansas City',
    shortName: 'SKC',
    logoUrl: `${APISPORTS_BASE}/1597.png`,
    primaryColor: '#91B0D5',
    initials: 'SKC',
  },
  'minnesota united': {
    name: 'Minnesota United',
    shortName: 'MIN',
    logoUrl: `${APISPORTS_BASE}/1601.png`,
    primaryColor: '#8CD2F4',
    initials: 'MIN',
  },
  'houston dynamo': {
    name: 'Houston Dynamo',
    shortName: 'HOU',
    logoUrl: `${APISPORTS_BASE}/1599.png`,
    primaryColor: '#FF6B00',
    initials: 'HOU',
  },
  'real salt lake': {
    name: 'Real Salt Lake',
    shortName: 'RSL',
    logoUrl: `${APISPORTS_BASE}/1606.png`,
    primaryColor: '#B30838',
    initials: 'RSL',
  },
  'colorado rapids': {
    name: 'Colorado Rapids',
    shortName: 'COL',
    logoUrl: `${APISPORTS_BASE}/1596.png`,
    primaryColor: '#862633',
    initials: 'COL',
  },
  'chicago fire': {
    name: 'Chicago Fire',
    shortName: 'CHI',
    logoUrl: `${APISPORTS_BASE}/1607.png`,
    primaryColor: '#C41230',
    initials: 'CHI',
  },
  'fc dallas': {
    name: 'FC Dallas',
    shortName: 'DAL',
    logoUrl: `${APISPORTS_BASE}/1602.png`,
    primaryColor: '#E03A3E',
    initials: 'DAL',
  },
  'charlotte fc': {
    name: 'Charlotte FC',
    shortName: 'CLT',
    logoUrl: `${APISPORTS_BASE}/18884.png`,
    primaryColor: '#1A85C8',
    initials: 'CLT',
  },
  'st. louis city sc': {
    name: 'St. Louis City SC',
    shortName: 'STL',
    logoUrl: `${APISPORTS_BASE}/20423.png`,
    primaryColor: '#E31937',
    initials: 'STL',
  },
  'vancouver whitecaps': {
    name: 'Vancouver Whitecaps',
    shortName: 'VAN',
    logoUrl: `${APISPORTS_BASE}/1612.png`,
    primaryColor: '#00245D',
    initials: 'VAN',
  },
  'new england revolution': {
    name: 'New England Revolution',
    shortName: 'NE',
    logoUrl: `${APISPORTS_BASE}/1615.png`,
    primaryColor: '#CE0E2D',
    initials: 'NER',
  },
  'san jose earthquakes': {
    name: 'San Jose Earthquakes',
    shortName: 'SJ',
    logoUrl: `${APISPORTS_BASE}/1616.png`,
    primaryColor: '#0067B1',
    initials: 'SJE',
  },
  'd.c. united': {
    name: 'D.C. United',
    shortName: 'DC',
    logoUrl: `${APISPORTS_BASE}/1617.png`,
    primaryColor: '#000000',
    initials: 'DCU',
  },

  // === LIGA PROFESIONAL ARGENTINA ===
  'river plate': {
    name: 'River Plate',
    shortName: 'RIV',
    logoUrl: `${FOTMOB_BASE}/10077.png`,
    primaryColor: '#EB1923',
    initials: 'RIV',
  },
  'boca juniors': {
    name: 'Boca Juniors',
    shortName: 'BOC',
    logoUrl: `${FOTMOB_BASE}/10076.png`,
    primaryColor: '#003399',
    initials: 'BOC',
  },
  'racing club': {
    name: 'Racing Club',
    shortName: 'RAC',
    logoUrl: `${FOTMOB_BASE}/10080.png`,
    primaryColor: '#0099FF',
    initials: 'RAC',
  },
  'san lorenzo': {
    name: 'San Lorenzo',
    shortName: 'SLO',
    logoUrl: `${FOTMOB_BASE}/10078.png`,
    primaryColor: '#003087',
    initials: 'SLO',
  },
  'independiente': {
    name: 'Independiente',
    shortName: 'IND',
    logoUrl: `${FOTMOB_BASE}/10079.png`,
    primaryColor: '#E20613',
    initials: 'IND',
  },
  'estudiantes': {
    name: 'Estudiantes',
    shortName: 'EDLP',
    logoUrl: `${FOTMOB_BASE}/10082.png`,
    primaryColor: '#E20613',
    initials: 'EST',
  },
  'estudiantes rio cuarto': {
    name: 'Estudiantes Río Cuarto',
    shortName: 'ERC',
    logoUrl: `${FOTMOB_BASE}/10082.png`,
    primaryColor: '#005BA9',
    initials: 'ERC',
  },
  'velez sarsfield': {
    name: 'Vélez Sarsfield',
    shortName: 'VEL',
    logoUrl: `${FOTMOB_BASE}/10083.png`,
    primaryColor: '#003399',
    initials: 'VEL',
  },
  'rosario central': {
    name: 'Rosario Central',
    shortName: 'CEN',
    logoUrl: `${FOTMOB_BASE}/10081.png`,
    primaryColor: '#003399',
    initials: 'ROS',
  },
  'newell\'s old boys': {
    name: "Newell's Old Boys",
    shortName: 'NOB',
    logoUrl: `${FOTMOB_BASE}/10085.png`,
    primaryColor: '#DA291C',
    initials: 'NOB',
  },
  'huracan': {
    name: 'Huracán',
    shortName: 'HUR',
    logoUrl: `${FOTMOB_BASE}/10086.png`,
    primaryColor: '#FFFFFF',
    initials: 'HUR',
  },
  'talleres': {
    name: 'Talleres',
    shortName: 'TAL',
    logoUrl: `${FOTMOB_BASE}/10091.png`,
    primaryColor: '#002B49',
    initials: 'TAL',
  },
  'defensa y justicia': {
    name: 'Defensa y Justicia',
    shortName: 'DYJ',
    logoUrl: `${FOTMOB_BASE}/188825.png`,
    primaryColor: '#008751',
    initials: 'DYJ',
  },
  'lanus': {
    name: 'Lanús',
    shortName: 'LAN',
    logoUrl: `${FOTMOB_BASE}/10088.png`,
    primaryColor: '#800000',
    initials: 'LAN',
  },
  'argentinos juniors': {
    name: 'Argentinos Juniors',
    shortName: 'ARG',
    logoUrl: `${FOTMOB_BASE}/10084.png`,
    primaryColor: '#DA291C',
    initials: 'AAAJ',
  },
  'banfield': {
    name: 'Banfield',
    shortName: 'BAN',
    logoUrl: `${FOTMOB_BASE}/10089.png`,
    primaryColor: '#008751',
    initials: 'BAN',
  },
  'belgrano': {
    name: 'Belgrano',
    shortName: 'BEL',
    logoUrl: `${FOTMOB_BASE}/10090.png`,
    primaryColor: '#6CABDD',
    initials: 'BEL',
  },
  'tigre': {
    name: 'Tigre',
    shortName: 'TIG',
    logoUrl: `${FOTMOB_BASE}/10092.png`,
    primaryColor: '#003399',
    initials: 'TIG',
  },
  'godoy cruz': {
    name: 'Godoy Cruz',
    shortName: 'GOD',
    logoUrl: `${FOTMOB_BASE}/10093.png`,
    primaryColor: '#003399',
    initials: 'GOD',
  },
  'barracas central': {
    name: 'Barracas Central',
    shortName: 'BAR',
    logoUrl: `${FOTMOB_BASE}/188827.png`,
    primaryColor: '#DA291C',
    initials: 'BAR',
  },
  'central cordoba (sde)': {
    name: 'Central Córdoba',
    shortName: 'CCO',
    logoUrl: `${FOTMOB_BASE}/10097.png`,
    primaryColor: '#000000',
    initials: 'CCO',
  },

  // === BRASILEIRÃO SÉRIE A ===
  'flamengo': {
    name: 'Flamengo',
    shortName: 'FLA',
    logoUrl: `${FOTMOB_BASE}/5981.png`,
    primaryColor: '#C4122D',
    initials: 'FLA',
  },
  'palmeiras': {
    name: 'Palmeiras',
    shortName: 'PAL',
    logoUrl: `${FOTMOB_BASE}/10283.png`,
    primaryColor: '#006437',
    initials: 'PAL',
  },
  'sao paulo': {
    name: 'São Paulo',
    shortName: 'SAO',
    logoUrl: `${FOTMOB_BASE}/10284.png`,
    primaryColor: '#DA291C',
    initials: 'SAO',
  },
  'corinthians': {
    name: 'Corinthians',
    shortName: 'COR',
    logoUrl: `${FOTMOB_BASE}/10281.png`,
    primaryColor: '#000000',
    initials: 'COR',
  },
  'fluminense': {
    name: 'Fluminense',
    shortName: 'FLU',
    logoUrl: `${FOTMOB_BASE}/10282.png`,
    primaryColor: '#800020',
    initials: 'FLU',
  },
  'gremio': {
    name: 'Grêmio',
    shortName: 'GRE',
    logoUrl: `${FOTMOB_BASE}/5926.png`,
    primaryColor: '#0D80BF',
    initials: 'GRE',
  },
  'internacional': {
    name: 'Internacional',
    shortName: 'INT',
    logoUrl: `${FOTMOB_BASE}/5982.png`,
    primaryColor: '#E20613',
    initials: 'INT',
  },
  'atletico mineiro': {
    name: 'Atlético Mineiro',
    shortName: 'CAM',
    logoUrl: `${FOTMOB_BASE}/10276.png`,
    primaryColor: '#000000',
    initials: 'CAM',
  },
  'botafogo': {
    name: 'Botafogo',
    shortName: 'BOT',
    logoUrl: `${FOTMOB_BASE}/5980.png`,
    primaryColor: '#000000',
    initials: 'BOT',
  },
  'cruzeiro': {
    name: 'Cruzeiro',
    shortName: 'CRU',
    logoUrl: `${FOTMOB_BASE}/5925.png`,
    primaryColor: '#003399',
    initials: 'CRU',
  },
  'vasco da gama': {
    name: 'Vasco da Gama',
    shortName: 'VAS',
    logoUrl: `${FOTMOB_BASE}/10277.png`,
    primaryColor: '#000000',
    initials: 'VAS',
  },
  'santos': {
    name: 'Santos',
    shortName: 'SAN',
    logoUrl: `${FOTMOB_BASE}/10274.png`,
    primaryColor: '#FFFFFF',
    initials: 'SAN',
  },
  'athletico paranaense': {
    name: 'Athletico-PR',
    shortName: 'CAP',
    logoUrl: `${FOTMOB_BASE}/10275.png`,
    primaryColor: '#C4122D',
    initials: 'CAP',
  },
  'bahia': {
    name: 'Bahia',
    shortName: 'BAH',
    logoUrl: `${FOTMOB_BASE}/10278.png`,
    primaryColor: '#005BA9',
    initials: 'BAH',
  },
  'fortaleza': {
    name: 'Fortaleza',
    shortName: 'FOR',
    logoUrl: `${FOTMOB_BASE}/10285.png`,
    primaryColor: '#003399',
    initials: 'FOR',
  },
  'red bull bragantino': {
    name: 'Red Bull Bragantino',
    shortName: 'RBB',
    logoUrl: `${FOTMOB_BASE}/10280.png`,
    primaryColor: '#DA291C',
    initials: 'RBB',
  },
  'vitoria': {
    name: 'Vitória',
    shortName: 'VIT',
    logoUrl: `${FOTMOB_BASE}/10289.png`,
    primaryColor: '#C4122D',
    initials: 'VIT',
  },
  'remo': {
    name: 'Remo',
    shortName: 'REM',
    logoUrl: `${FOTMOB_BASE}/10290.png`,
    primaryColor: '#002B49',
    initials: 'REM',
  },
};

// Aliases mapping common spellings to registry keys
const ALIASES: Record<string, string> = {
  'man city': 'manchester city',
  'mcfc': 'manchester city',
  'man utd': 'manchester united',
  'man united': 'manchester united',
  'mufc': 'manchester united',
  "nott'm forest": 'nottingham forest',
  'nottingham': 'nottingham forest',
  'spurs': 'tottenham',
  'palace': 'crystal palace',
  'wolves': 'wolves',
  'wolverhampton': 'wolves',
  'sheffield utd': 'sheffield united',

  'ath madrid': 'atletico madrid',
  'atletico': 'atletico madrid',
  'atlético': 'atletico madrid',
  'fc barcelona': 'barcelona',
  'barca': 'barcelona',
  'barça': 'barcelona',
  'real madrid cf': 'real madrid',
  'ath bilbao': 'athletic bilbao',
  'athletic club': 'athletic bilbao',
  'sociedad': 'real sociedad',
  'betis': 'real betis',
  'celta vigo': 'celta',
  'rayo': 'rayo vallecano',
  'depor': 'deportivo la coruna',
  'deportivo': 'deportivo la coruna',

  'inter milan': 'inter',
  'ac milan': 'milan',
  'roma': 'roma',
  'as roma': 'roma',
  'ss lazio': 'lazio',

  'bayern': 'bayern munich',
  'fc bayern': 'bayern munich',
  'bvb': 'dortmund',
  'borussia dortmund': 'dortmund',
  'bayer leverkusen': 'leverkusen',
  'leipzig': 'rb leipzig',
  'monchengladbach': "m'gladbach",
  'borussia m\'gladbach': "m'gladbach",
  'koln': 'fc koln',
  '1. fc koln': 'fc koln',

  'psg': 'paris sg',
  'paris saint-germain': 'paris sg',
  'paris saint germain': 'paris sg',
  'om': 'marseille',
  'ol': 'lyon',
  'as monaco': 'monaco',
  'stade brestois': 'brest',

  'kerala blasters': 'kerala blasters fc',
  'mumbai city': 'mumbai city fc',
  'mohun bagan': 'mohun bagan super giant',
  'atk mohun bagan': 'mohun bagan super giant',
  'east bengal': 'east bengal fc',
  'bengaluru': 'bengaluru fc',
  'goa': 'fc goa',
  'chennaiyin': 'chennaiyin fc',
  'hyderabad': 'hyderabad fc',
  'odisha': 'odisha fc',
  'jamshedpur': 'jamshedpur fc',
  'northeast united': 'northeast united fc',
  'punjab': 'punjab fc',
  'churchill brothers': 'churchill brothers sc',

  'inter miami': 'inter miami cf',
  'lafc': 'los angeles fc',
  'galaxy': 'la galaxy',
  'sounders': 'seattle sounders',
  'crew': 'columbus crew',
  'ny red bulls': 'new york red bulls',
  'nycfc': 'new york city fc',

  'river': 'river plate',
  'boca': 'boca juniors',
  'racing': 'racing club',
  'central cordoba': 'central cordoba (sde)',
  'central córdoba (sde)': 'central cordoba (sde)',
  'estudiantes de la plata': 'estudiantes',
  'estudiantes de rio cuarto': 'estudiantes rio cuarto',
  'estudiantes río cuarto': 'estudiantes rio cuarto',

  'são paulo': 'sao paulo',
  'sao paulo fc': 'sao paulo',
  'atletico-mg': 'atletico mineiro',
  'atlético mineiro': 'atletico mineiro',
  'athletico-pr': 'athletico paranaense',
  'vitória': 'vitoria',
};

/**
 * Normalizes team name by removing accents, lowercasing, and resolving aliases
 */
export function normalizeTeamName(name?: string | null): string {
  if (!name) return '';
  const clean = name
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // remove diacritics
    .replace(/[._-]/g, ' ')
    .replace(/\s+/g, ' ');

  if (ALIASES[clean]) {
    return ALIASES[clean];
  }
  return clean;
}

/**
 * Retrieves official team crest logo URL (FotMob / API-Sports CDN)
 */
export function getTeamLogoUrl(teamName?: string | null): string | null {
  if (!teamName) return null;
  const key = normalizeTeamName(teamName);
  const match = TEAM_REGISTRY[key];
  if (match && match.logoUrl) {
    return match.logoUrl;
  }
  return null;
}

/**
 * Generates FotMob-grade team styling metadata including initials and primary color
 */
export function getTeamMeta(teamName?: string | null): TeamLogoMeta {
  if (!teamName) {
    return {
      name: 'Unknown',
      shortName: 'UNK',
      initials: '??',
      primaryColor: '#334155',
    };
  }

  const key = normalizeTeamName(teamName);
  const match = TEAM_REGISTRY[key];
  if (match) {
    return match;
  }

  // Derive initials from words
  const parts = teamName.trim().split(/\s+/);
  let initials = '';
  if (parts.length >= 2) {
    initials = (parts[0][0] + parts[1][0]).toUpperCase();
  } else {
    initials = teamName.slice(0, 3).toUpperCase();
  }

  // Consistent dynamic color hash
  const colors = [
    '#EF4444', '#3B82F6', '#10B981', '#F59E0B',
    '#8B5CF6', '#EC4899', '#06B6D4', '#6366F1'
  ];
  let hash = 0;
  for (let i = 0; i < teamName.length; i++) {
    hash = (hash * 31 + teamName.charCodeAt(i)) & 0xffffffff;
  }
  const primaryColor = colors[Math.abs(hash) % colors.length];

  return {
    name: teamName,
    shortName: initials,
    initials,
    primaryColor,
  };
}
