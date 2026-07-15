"use client";
import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { Loader2 } from "lucide-react";

// Link de indicação (independente do ?ref= de afiliado): /convite/CODIGO só repassa o
// código pro formulário de cadastro via ?indicacao= — a validação de verdade é no backend.
export default function ConvitePage() {
  const router = useRouter();
  const params = useParams<{ code: string }>();

  useEffect(() => {
    const code = Array.isArray(params.code) ? params.code[0] : params.code;
    router.replace(`/cadastro?indicacao=${encodeURIComponent(code || "")}`);
  }, [params.code, router]);

  return (
    <div className="flex justify-center py-20">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
    </div>
  );
}
