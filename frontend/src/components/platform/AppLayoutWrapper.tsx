"use client";
import React, { useState, useEffect } from "react";
import Header from "@/components/platform/Header";
import Sidebar from "@/components/platform/Sidebar";
import Footer from "@/components/platform/Footer";
import { ArrowRightLeft } from "lucide-react";

const NAV_LAYOUT_KEY = "apostai_nav_layout";

export default function AppLayoutWrapper({ children }: { children: React.ReactNode }) {
  // Padrão: "sidebar" para o usuário experimentar a nova versão lateralizada imediatamente
  const [navLayout, setNavLayout] = useState<"sidebar" | "top">("sidebar");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem(NAV_LAYOUT_KEY);
      if (stored === "top" || stored === "sidebar") {
        setNavLayout(stored);
      }
    } catch {
      /* ignora */
    }
  }, []);

  const toggleLayout = () => {
    const next = navLayout === "sidebar" ? "top" : "sidebar";
    setNavLayout(next);
    try {
      localStorage.setItem(NAV_LAYOUT_KEY, next);
    } catch {
      /* ignora */
    }
  };

  const isSidebar = mounted && navLayout === "sidebar";

  return (
    <div className="relative flex min-h-screen flex-col">
      {/* Botão flutuante discreto no topo/canto para alternar modo de menu a qualquer momento */}
      <div className="fixed bottom-20 right-4 sm:bottom-6 sm:right-6 z-50">
        <button
          onClick={toggleLayout}
          className="shadow-xl bg-slate-900/90 text-white dark:bg-white/90 dark:text-slate-900 hover:opacity-90 transition-all duration-300 rounded-full px-3.5 py-2 text-xs font-bold flex items-center gap-2 backdrop-blur-md border border-slate-700/50 dark:border-slate-300/50"
        >
          <ArrowRightLeft className="w-3.5 h-3.5 text-emerald-400 dark:text-emerald-600" />
          <span>{isSidebar ? "Ver Menu no Topo" : "Ver Menu Lateral"}</span>
        </button>
      </div>

      {/* Header superior (visível se navLayout === "top" ou em dispositivos móveis) */}
      <div className={isSidebar ? "md:hidden" : ""}>
        <Header onToggleLayout={toggleLayout} navLayout={navLayout} />
      </div>

      {/* Sidebar lateral (visível em telas desktop quando navLayout === "sidebar") */}
      {isSidebar && <Sidebar navLayout={navLayout} onToggleLayout={toggleLayout} />}

      {/* Conteúdo principal (adiciona padding lateral md:pl-64 quando a sidebar está ativa) */}
      <main
        className={`flex-1 w-full max-w-7xl mx-auto p-4 pb-24 sm:p-6 md:pb-8 lg:p-8 animate-in fade-in duration-500 transition-all ${
          isSidebar ? "md:pl-72" : ""
        }`}
      >
        {children}
      </main>

      {/* Footer (recua se a sidebar estiver ativa no desktop) */}
      <div className={isSidebar ? "md:pl-64" : ""}>
        <Footer />
      </div>
    </div>
  );
}
