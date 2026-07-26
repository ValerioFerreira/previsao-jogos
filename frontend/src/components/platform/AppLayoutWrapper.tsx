"use client";
import React from "react";
import Header from "@/components/platform/Header";
import Footer from "@/components/platform/Footer";

export default function AppLayoutWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen flex-col">
      {/* Menu Superior Padrão */}
      <Header />

      {/* Conteúdo principal */}
      <main className="flex-1 w-full max-w-7xl mx-auto p-4 pb-24 sm:p-6 md:pb-8 lg:p-8 animate-in fade-in duration-500">
        {children}
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
}
