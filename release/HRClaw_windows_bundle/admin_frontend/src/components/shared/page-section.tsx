import { cn } from "@/lib/utils";

interface PageSectionProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function PageSection({
  title,
  description,
  actions,
  children,
  className,
}: PageSectionProps) {
  return (
    <section className={cn("space-y-5", className)}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-black/42">Section</div>
          <h2 className="mt-2 text-[40px] font-semibold leading-[1.1] tracking-[-0.03em] text-[#1d1d1f]">{title}</h2>
          {description ? <p className="mt-3 max-w-3xl text-[17px] leading-[1.47] tracking-[-0.022em] text-black/70">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
