"use client";
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutDashboard, Sparkles, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent } from "@/components/ui/card";

export default function ParceiroHubPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      if (!user) router.replace("/entrar");
      else router.replace("/parceiro/dashboard");
    }
  }, [loading, user, router]);

  return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
}
