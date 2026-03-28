import { CircleAlert, LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";

interface StatusBannerProps {
  tone?: "default" | "error" | "success";
  loading?: boolean;
  title: string;
  description?: string;
  className?: string;
}

const toneStyles = {
  default: "border-black/[0.06] bg-white/72 text-slate-700",
  error: "border-rose-200/80 bg-rose-50/82 text-rose-800",
  success: "border-emerald-200/80 bg-emerald-50/82 text-emerald-800",
};

export function StatusBanner({
  tone = "default",
  loading,
  title,
  description,
  className,
}: StatusBannerProps) {
  const Icon = loading ? LoaderCircle : CircleAlert;

  return (
    <div
      className={cn(
        "rounded-[24px] border px-4 py-4 shadow-[0_1px_0_rgba(255,255,255,0.86)_inset]",
        toneStyles[tone],
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 size-4 shrink-0", loading && "animate-spin")} />
        <div>
          <div className="text-sm font-semibold tracking-[-0.01em]">{title}</div>
          {description ? <div className="mt-1 text-sm leading-6 text-current/80">{description}</div> : null}
        </div>
      </div>
    </div>
  );
}
