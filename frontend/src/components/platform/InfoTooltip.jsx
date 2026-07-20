import React, { useState } from 'react';
import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// `href` opcional: transforma o ícone num link para a página "Como Funciona?" na seção
// que explica em detalhes aquele item.
export default function InfoTooltip({ text, side = "top", href, linkText = "Clique para ver a explicação completa →" }) {
  const [open, setOpen] = useState(false);

  const trigger = href ? (
    <a href={href} onClick={(e) => { if (!open) { e.preventDefault(); setOpen(true); } }} className="inline-flex items-center ml-1 text-muted-foreground hover:text-primary transition-colors" aria-label="Saiba mais">
      <Info className="w-3.5 h-3.5" />
    </a>
  ) : (
    <button type="button" onClick={(e) => { e.preventDefault(); setOpen(!open); }} className="inline-flex items-center ml-1 text-muted-foreground hover:text-foreground transition-colors">
      <Info className="w-3.5 h-3.5" />
    </button>
  );

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>{trigger}</TooltipTrigger>
        <TooltipContent side={side} className="max-w-xs text-xs leading-relaxed" onPointerDownOutside={() => setOpen(false)}>
          <p>{text}</p>
          {href && <p className="mt-1.5 text-primary font-medium">{linkText}</p>}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
