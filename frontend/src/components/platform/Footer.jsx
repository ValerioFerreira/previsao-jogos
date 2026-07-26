import React from 'react';
import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="border-t border-border/50 bg-card/40 mt-auto backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 space-y-2.5">
        {/* Texto descritivo mais longo no topo */}
        <p className="text-[10.5px] text-muted-foreground/60 leading-relaxed text-justify italic">
          Esta plataforma é uma ferramenta de análise quantitativa e inteligência preditiva. Projeções são estimativas baseadas em modelos matemáticos e não constituem garantia de resultados. O mercado esportivo envolve risco de capital. Utilize a inteligência estatística de forma consciente.
        </p>

        {/* Linha única abaixo: Aviso do ministério à esquerda e Termos/Créditos à direita */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-2.5 pt-2 border-t border-border/20 text-xs">
          <p className="text-[10.5px] sm:text-[11px] font-semibold text-amber-400/90 tracking-wide uppercase bg-amber-500/10 border border-amber-500/20 py-1 px-3 rounded-lg shadow-sm">
            ⚠️ Ministério da Fazenda adverte: aposta não é investimento
          </p>

          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Link href="/documentos" className="hover:text-foreground underline underline-offset-2 transition-colors">
              Termos & Privacidade
            </Link>
            <span className="text-muted-foreground/30 text-[10px]">|</span>
            <span>
              Desenvolvido pela <a href="https://safercode.com.br" target="_blank" rel="noopener noreferrer" className="hover:text-foreground underline transition-colors">SaferCode</a>
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}