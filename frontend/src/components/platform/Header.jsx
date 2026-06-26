"use client";
import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Sun, Moon, Activity, Wifi, WifiOff, BarChart3, Wrench } from 'lucide-react';
import { useTheme } from '@/lib/theme-context';
import { motion } from 'framer-motion';

const NAV_ITEMS = [
  { path: '/', label: 'Previsões' },
  { path: '/estatisticas', label: 'Estatísticas' },
  { path: '/construir-aposta', label: 'Construir Aposta' },
];

export default function Header() {
  const { theme, toggleTheme } = useTheme();
  const pathname = usePathname();
  const isConnected = true;
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2 shrink-0 min-h-[44px] min-w-[44px]">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <span className="font-heading font-bold text-base sm:text-lg tracking-tight flex items-center gap-0.5">
                Apost
                <span className="font-mono font-extrabold bg-gradient-to-br from-emerald-500 to-cyan-500 text-white px-1.5 py-0.5 rounded-md leading-none">AI</span>
                <span className="hidden sm:inline ml-1.5 text-xs font-normal text-muted-foreground tracking-normal">Tips and Stats</span>
              </span>
            </Link>

            {/* Navigation - Desktop */}
            <nav className="hidden md:flex items-center gap-1">
              {NAV_ITEMS.map(item => {
                const isActive = pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    href={item.path}
                    className="relative px-3 py-1.5 text-xs sm:text-sm font-medium transition-colors rounded-md min-h-[40px] flex items-center"
                  >
                    {isActive && (
                      <motion.div
                        layoutId="activeTab"
                        className="absolute inset-0 bg-primary/10 dark:bg-primary/20 rounded-md"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                    <span className={`relative z-10 ${isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                      {item.label}
                    </span>
                  </Link>
                );
              })}
            </nav>

            {/* Right Controls */}
            <div className="flex items-center gap-3 shrink-0">
              {/* API Status */}
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {isConnected ? (
                  <>
                    <Wifi className="w-3.5 h-3.5 text-emerald-500" />
                    <span className="hidden sm:inline">Conectado</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-3.5 h-3.5 text-red-500" />
                    <span className="hidden sm:inline">Desconectado</span>
                  </>
                )}
              </div>

              {/* Theme Toggle */}
              {mounted && (
                <button
                  onClick={toggleTheme}
                  className="p-2 rounded-lg hover:bg-accent transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
                  aria-label="Alternar tema"
                >
                  <motion.div
                    key={theme}
                    initial={{ rotate: -90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    transition={{ duration: 0.3 }}
                  >
                    {theme === 'dark' ? (
                      <Sun className="w-4 h-4 text-amber-400" />
                    ) : (
                      <Moon className="w-4 h-4 text-slate-600" />
                    )}
                  </motion.div>
                </button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Bottom Navigation for Mobile */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-background/90 border-t border-border/50 backdrop-blur-lg pb-safe">
        <div className="flex justify-around items-center h-16 px-2">
          {NAV_ITEMS.map(item => {
            const isActive = pathname === item.path;
            const Icon = item.path === '/' ? Activity : item.path === '/estatisticas' ? BarChart3 : Wrench;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex flex-col items-center justify-center flex-1 py-1 text-center text-[10px] font-medium transition-colors min-h-[48px] ${isActive ? 'text-primary' : 'text-muted-foreground'}`}
              >
                <Icon className={`w-5 h-5 mb-0.5 ${isActive ? 'text-primary' : 'text-muted-foreground'}`} />
                <span className={isActive ? 'text-foreground font-semibold' : ''}>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
