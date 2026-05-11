import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  variant?: "header" | "hero";
}

const variantClassNames: Record<NonNullable<BrandLogoProps["variant"]>, string> = {
  header: "h-8 w-auto md:h-9",
  hero: "w-[200px] max-w-full sm:w-[220px] md:w-[240px]",
};

export function BrandLogo({ className, variant = "header" }: BrandLogoProps) {
  const src =
    variant === "header"
      ? "/admin-static/HRCLAW-LOGO-MENU-0423.jpg?v=20260423"
      : "/admin-static/HRCLAW-LOGO-0423.png?v=20260423";
  return (
    <img
      src={src}
      alt="HRClaw"
      className={cn("select-none object-contain", variantClassNames[variant], className)}
      draggable={false}
      loading="eager"
      decoding="async"
    />
  );
}
