"use client";
import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Sun, Moon, Activity, BarChart3, Wrench, LayoutDashboard, ArrowRightLeft, Sparkles } from 'lucide-react';
import { useTheme } from '@/lib/theme-context';
import { useAuth } from '@/lib/AuthContext';
import { motion } from 'framer-motion';
import AccountMenu from '@/components/platform/AccountMenu';

export default function Header({ onToggleLayout, navLayout }) {
  const { theme, toggleTheme } = useTheme();
  const { user } = useAuth();
  const pathname = usePathname();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const isOwner = user && (user.role === 'owner' || user.email === 'valerioeducfin@gmail.com');
  const isPartner = user && user.role === 'partner';
  const showPartnerView = isOwner || isPartner;

  const navItems = [
    { path: '/', label: 'Análise' },
    { path: '/estatisticas', label: 'Estatísticas' },
    { path: '/como-funciona', label: 'Como Funciona?' },
  ];

  if (showPartnerView) {
    navItems.push({ path: '/parceiro/dashboard', label: 'Dashboard' });
  }

  return (
    <>
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-xl transition-colors">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between md:grid md:grid-cols-[1fr_auto_1fr] h-14 gap-4">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2.5 shrink-0 group justify-self-start">
              <div className="relative flex items-center justify-center">
                <img src="/images/so-o-A-sem-fundo.png" alt="ApostaInfo" className="w-7 h-7 sm:w-8 sm:h-8 object-contain transition-transform group-hover:scale-105" />
              </div>
              <img src="/images/so-o-texto-sem-fundo.png" alt="ApostaInfo" className="h-5 sm:h-6.5 w-auto object-contain" />
            </Link>

            {/* Navigation - Desktop */}
            <nav className="hidden md:flex items-center justify-center gap-2 justify-self-center">
              {navItems.map(item => {
                const isActive = pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    href={item.path}
                    className="relative px-4 py-1.5 text-sm font-semibold transition-colors rounded-xl flex items-center select-none"
                  >
                    {isActive && (
                      <motion.div
                        layoutId="activeTabHeader"
                        className="absolute inset-0 bg-accent/80 border border-border/60 rounded-xl shadow-sm"
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      />
                    )}
                    <span className={`relative z-10 ${isActive ? 'text-foreground font-bold' : 'text-muted-foreground hover:text-foreground'}`}>
                      {item.label}
                    </span>
                  </Link>
                );
              })}
            </nav>

            {/* Right Controls */}
            <div className="flex items-center gap-2 sm:gap-2.5 justify-self-end">
              {onToggleLayout && (
                <button
                  onClick={onToggleLayout}
                  className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-border/50 bg-muted/30 hover:bg-accent text-muted-foreground hover:text-foreground transition-all active:scale-[0.97]"
                  title="Alternar entre Menu Lateral e Menu no Topo"
                >
                  <ArrowRightLeft className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-[11px]">{navLayout === 'sidebar' ? 'Menu Topo' : 'Menu Lateral'}</span>
                </button>
              )}
              
              {/* Theme Toggle */}
              {mounted && (
                <button
                  onClick={toggleTheme}
                  className="p-2 rounded-lg border border-border/50 bg-muted/30 hover:bg-accent text-muted-foreground hover:text-foreground transition-all flex items-center justify-center active:scale-[0.96]"
                  aria-label="Alternar tema"
                >
                  <motion.div
                    key={theme}
                    initial={{ rotate: -90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    transition={{ duration: 0.2 }}
                  >
                    {theme === 'dark' ? (
                      <Sun className="w-4 h-4 text-amber-400" />
                    ) : (
                      <Moon className="w-4 h-4 text-slate-600" />
                    )}
                  </motion.div>
                </button>
              )}

              {/* Conta / créditos */}
              <AccountMenu />
            </div>
          </div>
        </div>
      </header>

      {/* Bottom Navigation for Mobile */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-background/95 border-t border-border/60 backdrop-blur-xl pb-safe">
        <div className="flex justify-around items-center h-15 px-2">
          {navItems.map(item => {
            const isActive = pathname === item.path;
            const Icon = item.path === '/' 
              ? Activity 
              : item.path === '/estatisticas' 
                ? BarChart3 
                : item.path === '/parceiro'
                  ? LayoutDashboard
                  : Wrench;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex flex-col items-center justify-center flex-1 py-1 text-center text-[10px] font-medium transition-colors ${isActive ? 'text-emerald-400' : 'text-muted-foreground'}`}
              >
                <Icon className={`w-4 h-4 mb-1 ${isActive ? 'text-emerald-400' : 'text-muted-foreground'}`} />
                <span className={isActive ? 'text-foreground font-bold' : ''}>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}

