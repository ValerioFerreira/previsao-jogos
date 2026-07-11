"use client";
import { useEffect } from "react";
import { captureReferralFromUrl } from "@/lib/affiliatesApi";

/** Captura ?ref=código de qualquer página pública e registra o clique (sem UI). */
export default function ReferralCapture() {
  useEffect(() => {
    captureReferralFromUrl();
  }, []);
  return null;
}
