"use client";
import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  BarChart3,
  Wrench,
  LayoutDashboard,
  Shield,
  Sun,
  Moon,
  Coins,
  LogOut,
  ArrowRightLeft
} from 'lucide-react';
import { useTheme } from '@/lib/theme-context';
import { useAuth } from '@/lib/AuthContext';
import { motion } from 'framer-motion';

interface SidebarProps {
  navLayout?: 'sidebar' | 'top';
  onToggleLayout?: () => void;
}

export default function Sidebar({ navLayout = 'sidebar', onToggleLayout }: SidebarProps) {
  const { theme, toggleTheme } = useTheme();
  const { user, wallet, logout } = useAuth();
  const pathname = usePathname();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const isOwner = user && (user.role === 'owner' || user.email === 'valerioeducfin@gmail.com');
  const isManager = user && user.role === 'manager';
  const isPartner = user && user.role === 'partner';
  const showPartnerView = isOwner || isPartner;
  const showAdminView = isOwner || isManager;

  const navItems = [
    { path: '/', label: 'Análise', icon: Activity },
    { path: '/estatisticas', label: 'Estatísticas', icon: BarChart3 },
    { path: '/como-funciona', label: 'Como Funciona?', icon: Wrench },
  ];

  if (showPartnerView) {
    navItems.push({ path: '/parceiro/dashboard', label: 'Dashboard', icon: LayoutDashboard });
  }

  if (showAdminView) {
    navItems.push({ path: '/admin', label: 'Painel Admin', icon: Shield });
  }

  const credits = wallet ? Math.floor(Number(wallet.available_balance)) : 0;
  const firstName = user ? user.full_name.split(' ')[0] : '';

  return (
    <aside className="hidden md:flex flex-col fixed left-0 top-0 bottom-0 w-64 bg-card/95 border-r border-border/60 z-50 backdrop-blur-xl transition-all duration-300">
      {/* Top Brand Section */}
      <div className="p-4 border-b border-border/50 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <img src="/images/so-o-A-sem-fundo.png" alt="ApostaInfo" className="w-8 h-8 object-contain" />
          <div className="flex flex-col">
            <img src="/images/so-o-texto-sem-fundo.png" alt="ApostaInfo" className="h-6 w-auto object-contain" />
            <span className="text-[10px] font-semibold text-emerald-500 uppercase tracking-widest -mt-1">
              Menu Lateral
            </span>
          </div>
        </Link>

        {onToggleLayout && (
          <button
            onClick={onToggleLayout}
            title="Alternar Layout"
            className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowRightLeft className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Card do Perfil do Usuário / Créditos (Posicionado logo acima do "Navegação") */}
      <div className="p-3 m-3 mb-1 rounded-xl bg-muted/50 border border-border/50 space-y-3">
        {user ? (
          <>
            <Link
              href="/perfil?tab=dados"
              className="flex items-center gap-2.5 group cursor-pointer hover:opacity-90 transition-opacity"
              title="Ir para o meu perfil"
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-white font-bold text-xs shadow-sm group-hover:scale-105 transition-transform">
                {firstName.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold truncate group-hover:text-primary transition-colors">
                  {user.full_name}
                </div>
                <div className="text-[10px] text-muted-foreground capitalize">
                  {user.role === 'owner' ? 'Proprietário' : user.role === 'partner' ? 'Parceiro' : 'Usuário'}
                </div>
              </div>
            </Link>

            <div className="flex items-center justify-between pt-2 border-t border-border/40">
              <Link
                href="/carteira"
                className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline"
                title="Ir para a carteira"
              >
                <Coins className="w-4 h-4" />
                <span>{credits} créditos</span>
              </Link>
              <Link
                href="/carteira"
                className="text-[11px] font-semibold text-primary hover:underline bg-primary/10 px-2 py-0.5 rounded"
              >
                + créditos
              </Link>
            </div>
          </>
        ) : (
          <div className="space-y-2 text-center py-1">
            <p className="text-xs text-muted-foreground">Acesse sua conta para utilizar créditos e gerar análises.</p>
            <Link
              href="/entrar"
              className="block w-full py-1.5 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition text-center"
            >
              Entrar na conta
            </Link>
          </div>
        )}
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-3 mb-2">
          Navegação
        </div>

        {navItems.map((item) => {
          const isActive = pathname === item.path;
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? 'bg-primary/10 text-primary font-semibold'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebarActiveIndicator"
                  className="absolute left-0 top-1.5 bottom-1.5 w-1 bg-primary rounded-r-full"
                  transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                />
              )}
              <Icon className={`w-4 h-4 ${isActive ? 'text-primary' : 'text-muted-foreground'}`} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer Actions */}
      <div className="p-3 border-t border-border/50 flex items-center justify-between gap-2">
        {mounted && (
          <button
            onClick={toggleTheme}
            aria-label="Alternar tema"
            className="flex-1 flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg hover:bg-accent transition-colors border border-border/60 text-xs font-medium"
          >
            {theme === 'dark' ? (
              <>
                <Sun className="w-4 h-4 text-amber-400" />
                <span>Modo Claro</span>
              </>
            ) : (
              <>
                <Moon className="w-4 h-4 text-slate-600" />
                <span>Modo Escuro</span>
              </>
            )}
          </button>
        )}

        {/* Logout */}
        {user && (
          <button
            onClick={logout}
            title="Sair da conta"
            className="p-2 rounded-lg hover:bg-red-500/10 text-red-600 transition-colors border border-border/60"
          >
            <LogOut className="w-4 h-4" />
          </button>
        )}
      </div>
    </aside>
  );
}
