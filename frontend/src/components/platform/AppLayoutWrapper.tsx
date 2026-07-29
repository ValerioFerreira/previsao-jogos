"use client";
import React, { useState, useEffect } from "react";
import Header from "@/components/platform/Header";
import Sidebar from "@/components/platform/Sidebar";
import Footer from "@/components/platform/Footer";

const NAV_LAYOUT_KEY = "apostai_nav_layout";
const SIDEBAR_COLLAPSED_KEY = "apostai_sidebar_collapsed";

export default function AppLayoutWrapper({ children }: { children: React.ReactNode }) {
  const [navLayout, setNavLayout] = useState<"sidebar" | "top">("top");
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem(NAV_LAYOUT_KEY);
      if (stored === "top" || stored === "sidebar") {
        setNavLayout(stored);
      }
      const storedCol = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
      if (storedCol === "true") {
        setIsCollapsed(true);
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

  const toggleCollapse = () => {
    const next = !isCollapsed;
    setIsCollapsed(next);
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
    } catch {
      /* ignora */
    }
  };

  const isSidebar = mounted && navLayout === "sidebar";

  return (
    <div className="relative flex min-h-screen flex-col bg-background selection:bg-emerald-500/20 selection:text-emerald-400">
      {/* Header superior (visível se menu for superior ou em mobile) */}
      <div className={isSidebar ? "md:hidden" : ""}>
        <Header onToggleLayout={toggleLayout} navLayout={navLayout} />
      </div>

      {/* Sidebar lateral (visível em telas md+ quando layout="sidebar") */}
      {isSidebar && (
        <Sidebar
          navLayout={navLayout}
          onToggleLayout={toggleLayout}
          isCollapsed={isCollapsed}
          onToggleCollapse={toggleCollapse}
        />
      )}

      {/* Container principal offset pelo sidebar para evitar sobreposição e centralizar no espaço visível */}
      <div
        className={`flex-1 flex flex-col min-w-0 w-full transition-all duration-300 ${
          isSidebar ? "md:pl-64" : ""
        }`}
      >
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 py-6 sm:px-6 md:py-8 lg:px-8">
          {children}
        </main>

        {/* Footer alinhado com a área visível */}
        <Footer />
      </div>
    </div>
  );
}
