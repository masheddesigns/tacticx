import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, Database, Cpu, BarChart2, ShieldCheck, Terminal } from 'lucide-react';
import { useReadyProbe } from '../../api/queries';

export const Navbar: React.FC = () => {
  const { data: ready } = useReadyProbe();
  const isHealthy = ready?.status === 'ok';

  const navItems = [
    { to: '/', label: 'Dashboard', icon: BarChart2 },
    { to: '/matches', label: 'Match Explorer', icon: Database },
    { to: '/system', label: 'System & Sources', icon: ShieldCheck },
    { to: '/monitoring', label: 'Monitoring', icon: Activity },
    { to: '/operations', label: 'Job Operations', icon: Terminal },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-surface-border bg-surface-base/90 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-2.5 focus:outline-none focus:ring-1 focus:ring-emerald-500 rounded p-1">
              <div className="w-8 h-8 rounded bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-mono font-bold text-base shadow-sm">
                TX
              </div>
              <div className="flex flex-col">
                <span className="font-bold text-sm tracking-tight text-slate-100 flex items-center gap-1.5">
                  TacticX
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-normal">
                    v1.7
                  </span>
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  Match Intelligence Platform
                </span>
              </div>
            </NavLink>

            <nav className="hidden md:flex items-center gap-1 pl-4 border-l border-surface-border" aria-label="Main Navigation">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                        isActive
                          ? 'bg-slate-800/80 text-emerald-400 border border-slate-700/60 shadow-inner'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                      }`
                    }
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-slate-900 border border-surface-border text-xs font-mono">
              <span
                className={`w-2 h-2 rounded-full ${
                  isHealthy ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : 'bg-amber-400'
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
      <div className="md:hidden flex border-t border-surface-border bg-slate-950 px-2 py-1.5 justify-around" aria-label="Mobile Navigation">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center py-1 px-2.5 rounded text-[10px] font-medium ${
                  isActive ? 'text-emerald-400' : 'text-slate-400 hover:text-slate-200'
                }`
              }
            >
              <Icon className="w-4 h-4 mb-0.5" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </header>
  );
};
