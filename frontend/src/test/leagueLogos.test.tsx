import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { getLeagueMeta, getLeagueLogoUrl, getLeagueFallbackEmoji } from '../lib/leagueLogos';
import { LeagueLogo } from '../components/common/LeagueLogo';

describe('Competition & League Logos Registry', () => {
  it('resolves authentic FotMob CDN URLs for all 10 major competitions', () => {
    // 1. Premier League
    expect(getLeagueLogoUrl('EPL')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/47.png');
    // 2. La Liga
    expect(getLeagueLogoUrl('LA_LIGA')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/87.png');
    // 3. Serie A
    expect(getLeagueLogoUrl('SERIE_A')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/55.png');
    // 4. Bundesliga
    expect(getLeagueLogoUrl('BUNDESLIGA')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/54.png');
    // 5. Ligue 1
    expect(getLeagueLogoUrl('LIGUE_1')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/53.png');
    // 6. UCL
    expect(getLeagueLogoUrl('UCL')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/42.png');
    // 7. MLS
    expect(getLeagueLogoUrl('MLS')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/130.png');
    // 8. Brazil Serie A
    expect(getLeagueLogoUrl('BRA_SERIE_A')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/268.png');
    // 9. Argentina Liga Profesional
    expect(getLeagueLogoUrl('LIGA_ARG')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/112.png');
    // 10. Indian Super League (ISL)
    expect(getLeagueLogoUrl('ISL')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/9478.png');
  });

  it('resolves natural language league aliases and variations', () => {
    expect(getLeagueLogoUrl('Premier League')).toContain('47.png');
    expect(getLeagueLogoUrl('Spanish La Liga')).toContain('87.png');
    expect(getLeagueLogoUrl('Indian Super League')).toContain('9478.png');
    expect(getLeagueLogoUrl('Major League Soccer')).toContain('130.png');
    expect(getLeagueLogoUrl('Brasileirão Série A')).toContain('268.png');
    expect(getLeagueLogoUrl('Liga Profesional')).toContain('112.png');
  });

  it('renders LeagueLogo component with image for registered competition', () => {
    render(<LeagueLogo league="EPL" size="lg" />);
    const img = screen.getByRole('img');
    expect(img).toBeInTheDocument();
    expect(img.getAttribute('src')).toBe('https://images.fotmob.com/image_resources/logo/leaguelogo/47.png');
  });

  it('gracefully renders fallback emoji when competition is unmapped or unknown', () => {
    render(<LeagueLogo league="Unknown League" size="md" />);
    const span = screen.getByRole('img');
    expect(span).toHaveTextContent('⚽');
  });
});
