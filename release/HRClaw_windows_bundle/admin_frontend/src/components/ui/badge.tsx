import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-[11px] font-medium tracking-[0.02em] transition-colors",
  {
    variants: {
      variant: {
        default: "border-[#d2d2d7] bg-[#f5f5f7] text-black/72",
        success: "border-[#b7d3f6] bg-[#eef5ff] text-[#0066cc]",
        warn: "border-amber-200/80 bg-amber-50/80 text-amber-700",
        danger: "border-rose-200/80 bg-rose-50/80 text-rose-700",
        neutral: "border-[#d2d2d7] bg-white text-black/62",
        info: "border-[#b7d3f6] bg-[#eef5ff] text-[#0066cc]",
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
