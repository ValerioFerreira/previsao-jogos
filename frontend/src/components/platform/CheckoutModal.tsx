"use client";
import React, { useState } from "react";
import { CreditCard, Loader2, QrCode, Tag } from "lucide-react";
import { paymentsApi, promotionsApi, type CreditPackage, type CouponPreview } from "@/lib/monetizationApi";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function CheckoutModal({
  pkg, open, onOpenChange, onConfirmed,
}: {
  pkg: CreditPackage | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmed: (result: { credits: number }) => void;
}) {
  const [couponCode, setCouponCode] = useState("");
  const [couponPreview, setCouponPreview] = useState<CouponPreview | null>(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponErr, setCouponErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // reseta o estado do cupom sempre que o modal é reaberto para um novo pacote
  React.useEffect(() => {
    if (open) {
      setCouponCode(""); setCouponPreview(null); setCouponErr(null); setErr(null);
    }
  }, [open, pkg?.id]);

  if (!pkg) return null;

  async function applyCoupon() {
    if (!couponCode.trim() || !pkg) return;
    setCouponBusy(true);
    setCouponErr(null);
    setCouponPreview(null);
    try {
      const preview = await promotionsApi.validateCoupon({
        code: couponCode.trim(), amount_brl: pkg.price_brl, credits: pkg.total_credits, package_id: pkg.id,
      });
      setCouponPreview(preview);
    } catch (e) {
      setCouponErr((e as Error).message);
    } finally {
      setCouponBusy(false);
    }
  }

  async function confirm() {
    if (!pkg) return;
    setBusy(true);
    setErr(null);
    try {
      const order = await paymentsApi.checkout({
        package_id: pkg.id,
        coupon_code: couponPreview ? couponCode.trim() : undefined,
      });
      if (order.provider === "mock") {
        await paymentsApi.mockConfirm(order.order_id);
        onConfirmed({ credits: order.credits });
        onOpenChange(false);
      } else {
        const initPoint = (order.checkout?.init_point as string | undefined)
          || (order.checkout?.sandbox_init_point as string | undefined);
        if (!initPoint) throw new Error("Checkout indisponível — tente novamente em instantes.");
        window.location.href = initPoint;
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const finalPrice = couponPreview ? Number(couponPreview.final_amount_brl) : Number(pkg.price_brl);
  const bonusFromCoupon = couponPreview?.bonus_credits || 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Confirmar compra</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border border-border/60 p-4">
            <div className="text-sm font-semibold">{pkg.name}</div>
            <div className="text-2xl font-bold mt-1">
              {pkg.total_credits + bonusFromCoupon} <span className="text-sm font-normal text-muted-foreground">créditos</span>
            </div>
            {(pkg.bonus_credits > 0 || bonusFromCoupon > 0) && (
              <div className="text-xs text-muted-foreground">
                {pkg.bonus_credits > 0 && `+${pkg.bonus_credits} bônus do pacote`}
                {pkg.bonus_credits > 0 && bonusFromCoupon > 0 && " · "}
                {bonusFromCoupon > 0 && `+${bonusFromCoupon} bônus do cupom`}
              </div>
            )}
            <div className="mt-2 text-lg font-semibold">
              R$ {finalPrice.toFixed(2)}
              {couponPreview && Number(couponPreview.original_amount_brl) !== finalPrice && (
                <span className="ml-2 text-xs text-muted-foreground line-through">R$ {Number(couponPreview.original_amount_brl).toFixed(2)}</span>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 flex items-center gap-1.5"><Tag className="w-3.5 h-3.5" /> Código promocional (opcional)</label>
            <div className="flex gap-2">
              <Input placeholder="Código promocional" value={couponCode}
                    onChange={(e) => { setCouponCode(e.target.value.toUpperCase()); setCouponPreview(null); setCouponErr(null); }} />
              <Button type="button" variant="outline" disabled={couponBusy || !couponCode.trim()} onClick={applyCoupon}>
                {couponBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Aplicar"}
              </Button>
            </div>
            {couponErr && <p className="text-xs text-red-600 mt-1.5">{couponErr}</p>}
            {couponPreview && <p className="text-xs text-emerald-600 mt-1.5">Cupom "{couponPreview.code}" aplicado.</p>}
          </div>

          <div className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground flex items-start gap-2">
            <div className="flex gap-1.5 shrink-0 mt-0.5"><QrCode className="w-4 h-4" /><CreditCard className="w-4 h-4" /></div>
            <span>Pagamento via PIX ou cartão, processado com segurança pelo Mercado Pago. Você escolhe o método na próxima etapa.</span>
          </div>

          {err && <p className="text-sm text-red-600">{err}</p>}

          <Button className="w-full" disabled={busy} onClick={confirm}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : `Confirmar e pagar — R$ ${finalPrice.toFixed(2)}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
