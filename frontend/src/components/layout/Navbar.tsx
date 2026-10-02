import React, { useState, useRef, useEffect } from 'react';
import { NavLink, Link } from 'react-router-dom';
import {
  Activity,
  Database,
  BarChart2,
  ShieldCheck,
  Terminal,
  FlaskConical,
  GitCompareArrows,
  Scale,
  Clock,
  Layers,
  ChevronDown,
} from 'lucide-react';
import { useReadyProbe, useUpcomingMatches } from '../../api/queries';

export const Navbar: React.FC = () => {
  const { data: ready } = useReadyProbe();
  const { data: upcoming } = useUpcomingMatches(72);
  const isHealthy = ready?.status === 'ok';
  const upcomingCount = upcoming?.data?.length || 0;

  const [platformMenuOpen, setPlatformMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setPlatformMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const primaryNavItems = [
    { to: '/', label: 'Matches', icon: Database },
    { to: '/matches', label: 'Explorer', icon: BarChart2 },
  ];

  const platformTools = [
    { to: '/system', label: 'System & Sources', icon: ShieldCheck, desc: 'Provider health and data acquisition' },
    { to: '/monitoring', label: 'Monitoring', icon: Activity, desc: 'Model performance and drift tracking' },
    { to: '/research', label: 'Research Lab', icon: FlaskConical, desc: 'Controlled candidate experiments' },
    { to: '/validation', label: 'Validation Gates', icon: ShieldCheck, desc: 'Real-world evidence validation' },
    { to: '/evidence', label: 'Evidence Audit', icon: Scale, desc: 'Cohort performance evidence' },
    { to: '/shadow', label: 'Shadow Models', icon: GitCompareArrows, desc: 'Champion vs challenger parallel runs' },
    { to: '/model-governance', label: 'Model Governance', icon: ShieldCheck, desc: 'Model promotions and registry' },
    { to: '/operations', label: 'Job Operations', icon: Terminal, desc: 'Distributed locks and job schedulers' },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-[#242938] bg-[#0e1015]/95 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-2.5 focus:outline-none focus:ring-1 focus:ring-[#21e786] rounded-lg p-1">
              <div className="w-8 h-8 rounded-lg bg-[#21e786]/10 border border-[#21e786]/30 flex items-center justify-center text-[#21e786] font-bold text-base shadow-sm">
                TX
              </div>
              <div className="flex flex-col">
                <span className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5 font-sans">
                  TacticX
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[#1e222e] text-slate-400 font-medium border border-[#242938]">
                    v1.7
                  </span>
                </span>
                <span className="text-[10px] text-slate-400 font-sans">
                  FotMob Match Intelligence
                </span>
              </div>
            </NavLink>

            <nav className="hidden md:flex items-center gap-1.5 pl-4 border-l border-[#242938]" aria-label="Main Navigation">
              {primaryNavItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold font-sans transition-all ${
                        isActive
                          ? 'bg-[#1e222e] text-[#21e786] border border-[#242938] shadow-sm'
                          : 'text-slate-400 hover:text-white hover:bg-[#161922]'
                      }`
                    }
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}

              <NavLink
                to="/matches?status=SCHEDULED"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium font-sans text-slate-400 hover:text-white hover:bg-[#161922] transition-colors"
              >
                <Clock className="w-3.5 h-3.5 text-[#21e786]" />
                <span>Upcoming</span>
                {upcomingCount > 0 && (
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-[#21e786]/10 text-[#21e786] border border-[#21e786]/30 font-semibold">
                    {upcomingCount}
                  </span>
                )}
              </NavLink>

              {/* Platform & Governance Dropdown */}
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setPlatformMenuOpen(!platformMenuOpen)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium font-sans transition-colors ${
                    platformMenuOpen
                      ? 'bg-[#1e222e] text-white border border-[#242938]'
                      : 'text-slate-400 hover:text-white hover:bg-[#161922]'
                  }`}
                >
                  <Layers className="w-3.5 h-3.5 text-purple-400" />
                  <span>Platform & MLOps</span>
                  <ChevronDown className={`w-3 h-3 transition-transform ${platformMenuOpen ? 'rotate-180' : ''}`} />
                </button>

                {platformMenuOpen && (
                  <div className="absolute left-0 mt-2 w-72 rounded-xl bg-[#161922] border border-[#242938] shadow-2xl py-2 z-50 divide-y divide-[#242938]">
                    <div className="px-3 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">
                      Platform Engineering & Governance
                    </div>
                    <div className="py-1">
                      {platformTools.map((tool) => {
                        const Icon = tool.icon;
                        return (
                          <Link
                            key={tool.to}
                            to={tool.to}
                            onClick={() => setPlatformMenuOpen(false)}
                            className="flex items-start gap-2.5 px-3 py-2 text-xs text-slate-300 hover:bg-[#1e222e] hover:text-white transition-colors"
                          >
                            <Icon className="w-4 h-4 text-[#21e786] mt-0.5 shrink-0" />
                            <div>
                              <div className="font-medium text-white">{tool.label}</div>
                              <div className="text-[10px] text-slate-400 font-sans">{tool.desc}</div>
                            </div>
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg bg-[#161922] border border-[#242938] text-xs font-mono">
              <span
                className={`w-2 h-2 rounded-full ${
                  isHealthy ? 'bg-[#21e786] shadow-[0_0_8px_rgba(33,231,134,0.7)]' : 'bg-amber-400'
                }`}
                aria-hidden="true"
              />
              <span className="text-[11px] text-slate-300">
                Engine: {isHealthy ? 'Operational' : 'Degraded'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Bar */}
      <div className="md:hidden flex border-t border-[#242938] bg-[#0e1015] px-2 py-1.5 justify-around" aria-label="Mobile Navigation">
        {primaryNavItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center py-1 px-2.5 rounded-lg text-[10px] font-medium font-sans ${
                  isActive ? 'text-[#21e786] font-bold' : 'text-slate-400 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 mb-0.5" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
        <NavLink
          to="/matches?status=SCHEDULED"
          className="flex flex-col items-center py-1 px-2.5 rounded-lg text-[10px] font-medium font-sans text-slate-400 hover:text-white"
        >
          <Clock className="w-4 h-4 mb-0.5 text-[#21e786]" />
          <span>Upcoming</span>
        </NavLink>
        <NavLink
          to="/system"
          className="flex flex-col items-center py-1 px-2.5 rounded-lg text-[10px] font-medium font-sans text-slate-400 hover:text-white"
        >
          <Layers className="w-4 h-4 mb-0.5 text-purple-400" />
          <span>Platform</span>
        </NavLink>
      </div>
    </header>
  );
};

