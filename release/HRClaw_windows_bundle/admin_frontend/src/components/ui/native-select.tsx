import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

type NativeSelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

interface NativeSelectExtraProps extends NativeSelectProps {
  iconClassName?: string;
}

export function NativeSelect({ className, iconClassName, children, ...props }: NativeSelectExtraProps) {
  return (
    <div className="relative">
      <select
        className={cn(
          "flex h-11 w-full appearance-none rounded-[11px] border border-[#d2d2d7] bg-[#fafafc] px-4 py-3 pr-11 text-[15px] text-[#1d1d1f] transition duration-200 focus-visible:border-[#0071e3] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0071e3]/25 disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className={cn(
          "pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-black/42",
          iconClassName,
        )}
      />
    </div>
  );
}
