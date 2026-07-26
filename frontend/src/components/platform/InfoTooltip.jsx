import React, { useState } from 'react';
import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export default function InfoTooltip({ text, side = "top", href, linkText = "Clique para ver a explicação completa →" }) {
  const [open, setOpen] = useState(false);

  const trigger = href ? (
    <a href={href} onClick={(e) => { if (!open) { e.preventDefault(); setOpen(true); } }} className="inline-flex items-center ml-1 text-muted-foreground/70 hover:text-emerald-400 transition-colors" aria-label="Saiba mais">
      <Info className="w-3.5 h-3.5" />
    </a>
  ) : (
    <button type="button" onClick={(e) => { e.preventDefault(); setOpen(!open); }} className="inline-flex items-center ml-1 text-muted-foreground/70 hover:text-foreground transition-colors">
      <Info className="w-3.5 h-3.5" />
    </button>
  );

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>{trigger}</TooltipTrigger>
        <TooltipContent side={side} className="max-w-xs text-xs leading-relaxed bg-popover/95 border-border/80 shadow-2xl backdrop-blur-md p-3 rounded-xl" onPointerDownOutside={() => setOpen(false)}>
          <p className="text-foreground/90">{text}</p>
          {href && <p className="mt-2 text-emerald-400 font-semibold underline underline-offset-2">{linkText}</p>}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

