import { cn } from "@/lib/utils";

interface StatTileProps {
  label: string;
  value: string | number;
  hint?: string;
  className?: string;
  density?: "default" | "compact";
}

export function StatTile({ label, value, hint, className, density = "default" }: StatTileProps) {
  const compact = density === "compact";
  return (
    <div
      className={cn(
        "rounded-xl bg-white transition-colors duration-200",
        compact ? "px-4 py-4" : "px-5 py-5",
        className,
      )}
    >
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-black/48">{label}</div>
      <div className={cn("font-semibold leading-[1.07] tracking-[-0.04em] text-[#1d1d1f]", compact ? "mt-2 text-[1.75rem]" : "mt-3 text-[2.45rem]")}>
        {value}
      </div>
      {hint ? (
        <div className={cn("text-black/68", compact ? "mt-1.5 text-[13px] leading-5" : "mt-2 text-[14px] leading-[1.43]")}>{hint}</div>
      ) : null}
    </div>
  );
}
