import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-[11px] font-medium tracking-[0.02em] transition-colors",
  {
    variants: {
      variant: {
        default: "border-black/[0.08] bg-black/[0.04] text-slate-700",
        success: "border-emerald-200/80 bg-emerald-50/80 text-emerald-700",
        warn: "border-amber-200/80 bg-amber-50/80 text-amber-700",
        danger: "border-rose-200/80 bg-rose-50/80 text-rose-700",
        neutral: "border-black/[0.08] bg-white/72 text-slate-600",
        info: "border-sky-200/80 bg-sky-50/80 text-sky-700",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
