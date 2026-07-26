import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/lib/theme-context";
import Header from "@/components/platform/Header";
import Footer from "@/components/platform/Footer";
import { Toaster } from "@/components/ui/toaster";
import { PredictionProvider } from "@/lib/PredictionContext";
import { AuthProvider } from "@/lib/AuthContext";
import ReferralCapture from "@/components/platform/ReferralCapture";
import InactivityWatcher from "@/components/platform/InactivityWatcher";
import SessionExpiredNotice from "@/components/platform/SessionExpiredNotice";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ApostaInfo - Análises Esportivas",
  description: "Análise quantitativa e previsão probabilística para partidas de futebol.",
  icons: {
    icon: [
      { url: "/images/favicon_io/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/images/favicon_io/favicon-16x16.png", sizes: "16x16", type: "image/png" }
    ],
    shortcut: "/images/favicon_io/favicon.ico",
    apple: "/images/favicon_io/apple-touch-icon.png",
  },
  manifest: "/images/favicon_io/site.webmanifest",
};

import AppLayoutWrapper from "@/components/platform/AppLayoutWrapper";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-background font-sans antialiased text-foreground selection:bg-primary/20 selection:text-primary`}>
        <ThemeProvider>
          <AuthProvider>
            <ReferralCapture />
            <InactivityWatcher />
            <SessionExpiredNotice />
            <PredictionProvider>
              <AppLayoutWrapper>{children}</AppLayoutWrapper>
              <Toaster />
            </PredictionProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
