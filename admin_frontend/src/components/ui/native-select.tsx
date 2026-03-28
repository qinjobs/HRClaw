import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

type NativeSelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

export function NativeSelect({ className, children, ...props }: NativeSelectProps) {
  return (
    <div className="relative">
      <select
        className={cn(
          "flex h-12 w-full appearance-none rounded-2xl border border-black/[0.08] bg-white/74 px-4 py-3 pr-11 text-sm text-slate-900 shadow-[0_1px_0_rgba(255,255,255,0.9)_inset] transition duration-200 focus-visible:border-slate-400 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-black/5 disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
    </div>
  );
}
