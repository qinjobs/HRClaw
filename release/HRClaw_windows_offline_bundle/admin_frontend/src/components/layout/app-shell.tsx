import { useLocation } from "react-router-dom";
import { LogOut } from "lucide-react";
import { motion } from "framer-motion";

import { adminNavItems } from "@/lib/constants";
import { postJson } from "@/lib/api";
import { cn } from "@/lib/utils";
import { BrandLogo } from "@/components/brand/brand-logo";
import { Button } from "@/components/ui/button";

interface AppShellProps {
  username?: string;
  userRole?: string;
  title: string;
  subtitle?: string;
  titleClassName?: string;
  subtitleClassName?: string;
  showPageTitle?: boolean;
  showWorkspacePanel?: boolean;
  children: React.ReactNode;
}

export function AppShell({
  username,
  userRole,
  title,
  subtitle,
  titleClassName,
  subtitleClassName,
  showPageTitle = true,
  showWorkspacePanel: _showWorkspacePanel = true,
  children,
}: AppShellProps) {
  const location = useLocation();
  const navItems = adminNavItems.filter((item) => !item.adminOnly || userRole === "admin");

  const logout = async () => {
    try {
      await postJson("/api/logout", {});
    } catch {
      // noop
    }
    window.location.href = "/login";
  };

  return (
    <div className="min-h-screen bg-[#f5f5f7]">
      <div className="mx-auto flex min-h-screen w-full max-w-[1680px] flex-col px-4 pb-24 pt-4 md:px-6 md:pb-28 lg:px-8">
        <header className="sticky top-4 z-40 rounded-full border border-black/[0.06] bg-[rgba(251,251,253,0.86)] px-4 py-3 shadow-[rgba(0,0,0,0.12)_0px_10px_24px_-18px] backdrop-blur-[24px] md:px-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-1 flex-col gap-4 lg:flex-row lg:items-center lg:gap-8">
              <div className="min-w-0 shrink-0">
                <BrandLogo variant="header" />
              </div>

              <nav className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1 lg:pb-0">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const active = location.pathname === item.href;
                  return (
                    <a
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-2 text-[12px] font-normal leading-none tracking-[-0.01em] transition-all duration-200",
                        active
                          ? "bg-black/[0.05] text-[#1d1d1f]"
                          : "text-black/72 hover:bg-black/[0.03] hover:text-[#1d1d1f]",
                      )}
                    >
                      <Icon className="size-[14px]" strokeWidth={1.8} />
                      {item.label}
                    </a>
                  );
                })}
              </nav>
            </div>

            <div className="flex shrink-0 items-center gap-2 self-start lg:self-auto">
              <div className="hidden rounded-full bg-black/[0.04] px-4 py-2 text-[12px] text-black/62 md:block">
                用户：<span className="font-semibold text-[#1d1d1f]">{username || "admin"}</span>
              </div>
              <Button size="sm" variant="secondary" onClick={logout}>
                <LogOut className="size-4" />
                退出
              </Button>
            </div>
          </div>
        </header>

        <main
          className={cn("flex-1", showPageTitle ? "pt-6 md:pt-8" : "pt-4 md:pt-6")}
          style={{ paddingBottom: "max(3.5rem, env(safe-area-inset-bottom))" }}
        >
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
            className="space-y-6 pb-10 md:pb-14"
          >
            {showPageTitle ? (
              <section className="grid gap-4 xl:grid-cols-1">
                <div className="space-y-3">
                  <div className="max-w-5xl 2xl:max-w-6xl">
                    <h1
                      className={cn(
                        "text-[34px] font-semibold leading-[1.08] tracking-[-0.04em] text-[#1d1d1f] md:text-[46px]",
                        titleClassName,
                      )}
                    >
                      {title}
                    </h1>
                    {subtitle ? (
                      <p className={cn("mt-3 max-w-4xl text-[16px] leading-[1.45] tracking-[-0.02em] text-black/70", subtitleClassName)}>{subtitle}</p>
                    ) : null}
                  </div>
                </div>
              </section>
            ) : null}

            {children}
          </motion.div>
        </main>
      </div>
    </div>
  );
}
