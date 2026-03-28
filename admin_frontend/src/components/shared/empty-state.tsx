import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-[220px] flex-col items-center justify-center rounded-[30px] border border-dashed border-black/[0.08] bg-white/56 px-8 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.82)]",
        className,
      )}
    >
      <div className="max-w-sm">
        <div className="text-lg font-semibold tracking-[-0.03em] text-slate-900">{title}</div>
        <p className="mt-3 text-sm leading-7 text-slate-500">{description}</p>
        {actionLabel && onAction ? (
          <Button className="mt-5" variant="secondary" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
