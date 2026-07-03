"use client";
import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { legalApi } from "@/lib/monetizationApi";
import { Card, CardContent } from "@/components/ui/card";

export default function DocumentoPage() {
  const params = useParams();
  const type = String(params.type);
  const [doc, setDoc] = useState<{ title: string; version: number; body_md: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    legalApi.document(type).then(setDoc).catch((e) => setErr((e as Error).message));
  }, [type]);

  if (err) return <div className="max-w-3xl mx-auto text-sm text-red-600">{err}</div>;
  if (!doc) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-3xl mx-auto">
      <Card>
        <CardContent className="pt-6 prose prose-sm dark:prose-invert max-w-none">
          <div className="text-xs text-muted-foreground mb-2">Versão {doc.version}</div>
          {/* renderizacao simples de markdown (paragrafos e titulos) */}
          {doc.body_md.split("\n").map((line, i) => {
            if (line.startsWith("# ")) return <h1 key={i} className="text-xl font-bold mt-2 mb-3">{line.slice(2)}</h1>;
            if (line.startsWith("## ")) return <h2 key={i} className="text-lg font-semibold mt-3 mb-2">{line.slice(3)}</h2>;
            if (!line.trim()) return <div key={i} className="h-2" />;
            return <p key={i} className="text-sm text-muted-foreground leading-relaxed">{line}</p>;
          })}
        </CardContent>
      </Card>
    </div>
  );
}
