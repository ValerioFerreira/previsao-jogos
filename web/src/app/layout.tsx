import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Previsao de Jogos",
  description: "Previsoes de partidas de selecoes com API Python e modelos scikit-learn.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

