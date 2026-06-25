import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/lib/theme-context";
import Header from "@/components/platform/Header";
import Footer from "@/components/platform/Footer";
import { Toaster } from "@/components/ui/toaster";
import { PredictionProvider } from "@/lib/PredictionContext";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Honestidade Probabilística | Previsões",
  description: "Análise quantitativa e previsão probabilística para partidas de futebol de seleções.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-background font-sans antialiased text-foreground selection:bg-primary/20 selection:text-primary`}>
        <ThemeProvider>
          <PredictionProvider>
            <div className="relative flex min-h-screen flex-col">
              <Header />
              <main className="flex-1 w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
                {children}
              </main>
              <Footer />
            </div>
            <Toaster />
          </PredictionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
