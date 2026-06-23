import React from 'react';

export default function Footer() {
  return (
    <footer className="border-t border-border/50 bg-muted/30 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
        <p className="text-[11px] sm:text-xs text-muted-foreground/70 leading-relaxed text-center italic">
          Esta plataforma é uma ferramenta de análise estatística baseada em modelos matemáticos e distribuições de probabilidade. Projeções não são certezas e não constituem garantia de lucro. O mercado esportivo envolve volatilidade e risco inerente de perda de capital. Utilize os dados de forma analítica e consciente.
        </p>
      </div>
    </footer>
  );
}