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
        "rounded-[28px] border border-black/[0.06] bg-white/72 shadow-[0_1px_0_rgba(255,255,255,0.92)_inset] backdrop-blur-xl transition-transform duration-200 hover:-translate-y-0.5 hover:bg-white/82",
        compact ? "px-4 py-4" : "px-5 py-5",
        className,
      )}
    >
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">{label}</div>
      <div className={cn("font-semibold tracking-[-0.05em] text-slate-950", compact ? "mt-2 text-[1.75rem]" : "mt-3 text-[2rem]")}>
        {value}
      </div>
      {hint ? (
        <div className={cn("text-slate-500", compact ? "mt-1.5 text-[13px] leading-5" : "mt-2 text-sm leading-6")}>{hint}</div>
      ) : null}
    </div>
  );
}
