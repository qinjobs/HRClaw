import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  variant?: "header" | "hero";
}

const variantClassNames: Record<NonNullable<BrandLogoProps["variant"]>, string> = {
  header: "h-11 w-auto md:h-12",
  hero: "w-[200px] max-w-full sm:w-[220px] md:w-[240px]",
};

export function BrandLogo({ className, variant = "header" }: BrandLogoProps) {
  return (
    <img
      src="/admin-static/logo.jpg?v=20260328"
      alt="HRClaw"
      className={cn("select-none object-contain", variantClassNames[variant], className)}
      draggable={false}
      loading="eager"
      decoding="async"
    />
  );
}
