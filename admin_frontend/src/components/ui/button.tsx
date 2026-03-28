import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium tracking-[-0.01em] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/10 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 shrink-0 active:translate-y-[0.5px]",
  {
    variants: {
      variant: {
        default:
          "border border-slate-950 bg-slate-950 text-white shadow-[0_1px_1px_rgba(15,23,42,0.12),0_10px_24px_-16px_rgba(15,23,42,0.45)] hover:bg-slate-800 hover:shadow-[0_1px_1px_rgba(15,23,42,0.12),0_14px_28px_-18px_rgba(15,23,42,0.55)]",
        secondary:
          "border border-black/[0.08] bg-white/86 text-slate-700 shadow-[0_1px_0_rgba(255,255,255,0.92)_inset,0_8px_18px_-16px_rgba(15,23,42,0.18)] backdrop-blur-xl hover:bg-white hover:text-slate-950",
        outline:
          "border border-black/[0.08] bg-black/[0.02] text-slate-700 hover:bg-black/[0.04] hover:text-slate-950",
        ghost: "text-slate-600 hover:bg-black/[0.04] hover:text-slate-950",
        subtle: "bg-black/[0.04] text-slate-700 hover:bg-black/[0.06] hover:text-slate-950",
        destructive: "border border-rose-200 bg-rose-600 text-white shadow-[0_10px_24px_-16px_rgba(225,29,72,0.45)] hover:bg-rose-500",
      },
      size: {
        default: "h-11 px-5 py-2",
        sm: "h-9 px-4 text-[13px]",
        lg: "h-12 px-6 text-base",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
