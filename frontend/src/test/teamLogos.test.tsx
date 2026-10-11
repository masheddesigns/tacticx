import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { normalizeTeamName, getTeamLogoUrl, getTeamMeta } from '../lib/teamLogos';
import { TeamLogo } from '../components/common/TeamLogo';

describe('Team Logos & Crests', () => {
  it('resolves FotMob CDN URLs for European top clubs', () => {
    const arsenalLogo = getTeamLogoUrl('Arsenal');
    expect(arsenalLogo).toContain('images.fotmob.com');
    expect(arsenalLogo).toContain('9825.png');

    const realMadridLogo = getTeamLogoUrl('Real Madrid');
    expect(realMadridLogo).toContain('images.fotmob.com');
    expect(realMadridLogo).toContain('8633.png');

    const manCityLogo = getTeamLogoUrl('Man City');
    expect(manCityLogo).toContain('images.fotmob.com');
    expect(manCityLogo).toContain('8456.png');
  });

  it('resolves authentic FotMob CDN URLs for ISL, MLS, Argentina, and Brazil clubs', () => {
    const keralaBlasters = getTeamLogoUrl('Kerala Blasters FC');
    expect(keralaBlasters).toContain('images.fotmob.com');
    expect(keralaBlasters).toContain('578654.png');

    const interMiami = getTeamLogoUrl('Inter Miami CF');
    expect(interMiami).toContain('images.fotmob.com');
    expect(interMiami).toContain('960720.png');

    const riverPlate = getTeamLogoUrl('River Plate');
    expect(riverPlate).toContain('images.fotmob.com');
    expect(riverPlate).toContain('10076.png');

    const flamengo = getTeamLogoUrl('Flamengo');
    expect(flamengo).toContain('images.fotmob.com');
    expect(flamengo).toContain('9770.png');
  });

  it('normalizes accents, diacritics, and aliases correctly', () => {
    expect(normalizeTeamName("Nott'm Forest")).toBe('nottingham forest');
    expect(normalizeTeamName('Atlético Madrid')).toBe('atletico madrid');
    expect(normalizeTeamName('São Paulo')).toBe('sao paulo');
    expect(normalizeTeamName('FC Barcelona')).toBe('barcelona');
  });

  it('gracefully handles unknown teams with colored monogram fallback', () => {
    const meta = getTeamMeta('Random FC');
    expect(meta.name).toBe('Random FC');
    expect(meta.initials).toBe('RF');
    expect(meta.primaryColor).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(meta.logoUrl).toBeUndefined();
  });

  it('renders TeamLogo component image when logo exists', () => {
    render(<TeamLogo teamName="Arsenal" size="md" />);
    const img = screen.getByRole('img');
    expect(img).toBeDefined();
    expect(img.getAttribute('src')).toContain('9825.png');
    expect(img.getAttribute('alt')).toBe('Arsenal');
  });

  it('renders fallback badge when team logo does not exist', () => {
    render(<TeamLogo teamName="Nonexistent Club" size="md" />);
    const initialsBadge = screen.getByText('NC');
    expect(initialsBadge).toBeDefined();
  });
});
