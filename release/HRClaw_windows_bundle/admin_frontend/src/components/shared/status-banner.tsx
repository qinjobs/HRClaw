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
  default: "bg-[#f5f5f7] text-[#1d1d1f]",
  error: "bg-rose-50 text-rose-800",
  success: "bg-[#eef5ff] text-[#0066cc]",
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
        "rounded-[12px] px-4 py-4",
        toneStyles[tone],
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 size-4 shrink-0", loading && "animate-spin")} />
        <div>
          <div className="text-[15px] font-semibold tracking-[-0.022em]">{title}</div>
          {description ? <div className="mt-1 text-[14px] leading-[1.43] text-current/78">{description}</div> : null}
        </div>
      </div>
    </div>
  );
}
