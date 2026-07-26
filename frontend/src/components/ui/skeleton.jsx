import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}) {
  return (
    <div
      className={cn("animate-shimmer rounded-lg bg-muted/40 border border-white/5", className)}
      {...props}
    />
  );
}

export { Skeleton }

