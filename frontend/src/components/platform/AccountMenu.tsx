"use client";
import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Coins, LogOut, User as UserIcon, Wallet as WalletIcon } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function AccountMenu() {
  const { user, wallet, loading, logout } = useAuth();
  const router = useRouter();

  if (loading) return <div className="h-8 w-16 rounded-md bg-muted animate-pulse" />;

  if (!user) {
    return (
      <Link
        href="/entrar"
        className="px-3 py-1.5 text-xs sm:text-sm font-semibold rounded-md bg-primary text-primary-foreground hover:opacity-90 transition"
      >
        Entrar
      </Link>
    );
  }

  const credits = wallet ? Math.floor(Number(wallet.available_balance)) : 0;
  const firstName = user.full_name.split(" ")[0];

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/carteira"
        title="Créditos disponíveis"
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs sm:text-sm font-semibold hover:bg-emerald-500/20 transition"
      >
        <Coins className="w-3.5 h-3.5" />
        {credits}
        <span className="hidden sm:inline font-normal text-muted-foreground">créditos</span>
      </Link>

      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-accent transition outline-none">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-white text-xs font-bold">
            {firstName.charAt(0).toUpperCase()}
          </div>
          <span className="hidden sm:inline text-xs sm:text-sm font-medium">{firstName}</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel className="truncate">{user.email}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link href="/perfil" className="cursor-pointer">
              <UserIcon className="w-4 h-4 mr-2" /> Meu perfil
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/carteira" className="cursor-pointer">
              <WalletIcon className="w-4 h-4 mr-2" /> Carteira
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="cursor-pointer text-red-600 dark:text-red-400"
            onClick={() => {
              logout();
              router.push("/");
            }}
          >
            <LogOut className="w-4 h-4 mr-2" /> Sair
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
