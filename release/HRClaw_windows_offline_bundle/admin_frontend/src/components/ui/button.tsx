import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-[15px] font-medium tracking-[-0.022em] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0071e3] focus-visible:ring-offset-2 focus-visible:ring-offset-transparent disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 shrink-0 active:translate-y-[0.5px]",
  {
    variants: {
      variant: {
        default:
          "border border-transparent bg-[#0071e3] text-white hover:bg-[#0077ed]",
        secondary:
          "border border-[#d2d2d7] bg-white text-[#1d1d1f] hover:bg-[#fbfbfd]",
        outline:
          "border border-[#0071e3] bg-transparent text-[#0066cc] hover:bg-[#0071e3] hover:text-white",
        ghost: "text-[#0066cc] hover:bg-[#0071e3]/[0.08] hover:text-[#0066cc]",
        subtle: "border border-transparent bg-[#1d1d1f] text-white hover:bg-black",
        destructive: "border border-rose-200 bg-rose-600 text-white hover:bg-rose-500",
      },
      size: {
        default: "h-10 px-5 py-2",
        sm: "h-9 px-4 text-[13px]",
        lg: "h-12 px-6 text-base",
        icon: "h-10 w-10",
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
