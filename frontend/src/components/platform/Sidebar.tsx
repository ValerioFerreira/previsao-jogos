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
  ArrowRightLeft,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useTheme } from '@/lib/theme-context';
import { useAuth } from '@/lib/AuthContext';
import { motion } from 'framer-motion';

interface SidebarProps {
  navLayout?: 'sidebar' | 'top';
  onToggleLayout?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function Sidebar({
  navLayout = 'sidebar',
  onToggleLayout,
  isCollapsed = false,
  onToggleCollapse,
}: SidebarProps) {
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
    <aside
      className={`hidden md:flex flex-col fixed left-0 top-0 bottom-0 bg-card/95 border-r border-border/60 z-50 backdrop-blur-xl transition-all duration-300 shadow-2xl ${
        isCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Top Brand Section */}
      <div className={`p-3.5 border-b border-border/50 flex items-center justify-between gap-2 ${isCollapsed ? 'px-2 justify-center' : 'px-4'}`}>
        <Link href="/" className="flex items-center gap-3 min-w-0 flex-1 overflow-hidden">
          <img src="/images/so-o-A-sem-fundo.png" alt="ApostaInfo" className="w-10 h-10 object-contain shrink-0 drop-shadow" />
          {!isCollapsed && (
            <div className="flex-1 flex justify-center min-w-0">
              <img src="/images/so-o-texto-sem-fundo.png" alt="ApostaInfo" className="h-7 sm:h-7.5 w-auto object-contain" />
            </div>
          )}
        </Link>

        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            title={isCollapsed ? "Expandir barra lateral" : "Colapsar barra lateral"}
            className="p-1.5 rounded-xl hover:bg-accent text-muted-foreground hover:text-foreground transition-all shrink-0 cursor-pointer active:scale-95"
          >
            {isCollapsed ? (
              <PanelLeftOpen className="w-5 h-5 text-emerald-400" />
            ) : (
              <PanelLeftClose className="w-5 h-5 text-muted-foreground hover:text-foreground" />
            )}
          </button>
        )}
      </div>

      {/* Card do Perfil do Usuário / Créditos */}
      {!isCollapsed ? (
        <div className="p-3 m-3 mb-1 rounded-xl bg-muted/40 border border-border/50 space-y-3">
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
                  <div className="text-[10px] text-muted-foreground capitalize font-mono">
                    {user.role === 'owner' ? 'Proprietário' : user.role === 'partner' ? 'Parceiro' : 'Usuário'}
                  </div>
                </div>
              </Link>

              <div className="flex items-center justify-between pt-2 border-t border-border/40">
                <Link
                  href="/carteira"
                  className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline font-mono"
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
      ) : (
        <div className="py-3 flex flex-col items-center border-b border-border/40">
          {user ? (
            <Link href="/carteira" title={`${credits} créditos - Ir para a carteira`} className="flex flex-col items-center gap-1">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-white font-bold text-xs shadow-sm">
                {firstName.charAt(0).toUpperCase()}
              </div>
              <span className="text-xs font-black font-mono text-emerald-400 tracking-tight bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">{credits}c</span>
            </Link>
          ) : (
            <Link href="/entrar" title="Entrar na conta" className="p-1 text-xs text-emerald-400 font-bold">
              🔑
            </Link>
          )}
        </div>
      )}

      {/* Main Navigation */}
      <nav className={`flex-1 space-y-1 overflow-y-auto ${isCollapsed ? 'px-2 py-4' : 'px-3 py-3'}`}>
        {!isCollapsed && (
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-3 mb-2 font-mono">
            Navegação
          </div>
        )}

        {navItems.map((item) => {
          const isActive = pathname === item.path;
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              href={item.path}
              title={item.label}
              className={`relative flex items-center gap-3 rounded-xl transition-all ${
                isCollapsed ? 'justify-center p-3' : 'px-3 py-2.5 text-sm font-semibold'
              } ${
                isActive
                  ? 'bg-primary/10 text-primary font-bold shadow-sm'
                  : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
              }`}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebarActiveIndicator"
                  className="absolute left-0 top-1.5 bottom-1.5 w-1 bg-primary rounded-r-full"
                  transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                />
              )}
              <Icon className={`w-5 h-5 ${isActive ? 'text-primary' : 'text-muted-foreground'}`} />
              {!isCollapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer Actions */}
      <div className={`p-3 border-t border-border/50 flex items-center gap-2 bg-card/40 ${isCollapsed ? 'flex-col justify-center px-2' : 'justify-between'}`}>
        {/* Seletor entre lua e sol somente */}
        {mounted && (
          <button
            onClick={toggleTheme}
            aria-label="Alternar tema"
            title="Alternar Tema (Claro / Escuro)"
            className={`rounded-xl border border-border/60 bg-muted/30 hover:bg-accent text-muted-foreground hover:text-foreground transition-all flex items-center justify-center cursor-pointer active:scale-95 shrink-0 ${
              isCollapsed ? 'p-2.5 w-full' : 'p-2.5'
            }`}
          >
            {theme === 'dark' ? (
              <Sun className="w-4.5 h-4.5 text-amber-400" />
            ) : (
              <Moon className="w-4.5 h-4.5 text-slate-600" />
            )}
          </button>
        )}

        {/* Botão de Alternar para Menu Superior */}
        {onToggleLayout && (
          <button
            onClick={onToggleLayout}
            title="Alternar para Menu Superior"
            className={`flex items-center justify-center gap-2 rounded-xl border border-border/60 bg-muted/30 hover:bg-accent text-muted-foreground hover:text-foreground transition-all text-xs font-semibold cursor-pointer active:scale-95 ${
              isCollapsed ? 'p-2.5 w-full' : 'flex-1 py-2 px-3'
            }`}
          >
            <ArrowRightLeft className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            {!isCollapsed && <span>Menu Superior</span>}
          </button>
        )}

        {/* Logout */}
        {user && (
          <button
            onClick={logout}
            title="Sair da conta"
            className={`rounded-xl hover:bg-red-500/10 text-red-500 transition-all border border-border/60 shrink-0 cursor-pointer active:scale-95 ${
              isCollapsed ? 'p-2.5 w-full' : 'p-2.5'
            }`}
          >
            <LogOut className="w-4 h-4" />
          </button>
        )}
      </div>
    </aside>
  );
}
