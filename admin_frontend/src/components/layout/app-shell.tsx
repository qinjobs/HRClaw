import { useLocation, useNavigate } from "react-router-dom";
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
  showPageTitle = false,
  showWorkspacePanel = true,
  children,
}: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
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
    <div className="min-h-screen">
      <div className="mx-auto flex min-h-screen w-full max-w-[1760px] flex-col px-4 pb-24 pt-4 md:px-6 md:pb-28 lg:px-8 2xl:max-w-[1880px] 2xl:px-10">
        <header className="sticky top-4 z-40 rounded-[30px] border border-black/[0.06] bg-white/76 px-4 py-4 shadow-[0_24px_60px_-36px_rgba(15,23,42,0.28)] backdrop-blur-2xl md:px-6">
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
                        "inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium tracking-[-0.01em] transition-all duration-200",
                        active
                          ? "border border-slate-950 bg-slate-950 text-white shadow-[0_10px_24px_-16px_rgba(15,23,42,0.45)]"
                          : "border border-transparent text-slate-500 hover:border-black/[0.06] hover:bg-white/74 hover:text-slate-950",
                      )}
                    >
                      <Icon className="size-4" />
                      {item.label}
                    </a>
                  );
                })}
              </nav>
            </div>

            <div className="flex shrink-0 items-center gap-2 self-start lg:self-auto">
              <div className="hidden rounded-full border border-black/[0.06] bg-white/72 px-4 py-2 text-sm text-slate-500 md:block">
                用户：<span className="font-semibold text-slate-950">{username || "admin"}</span>
              </div>
              <Button variant="secondary" onClick={logout}>
                <LogOut className="size-4" />
                退出
              </Button>
            </div>
          </div>
        </header>

        <main
          className={cn("flex-1", showPageTitle ? "pt-8 md:pt-10" : "pt-4 md:pt-6")}
          style={{ paddingBottom: "max(3.5rem, env(safe-area-inset-bottom))" }}
        >
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
            className="space-y-8 pb-10 md:pb-14"
          >
            {showPageTitle ? (
              <section
                className={cn(
                  "grid gap-5",
                  showWorkspacePanel
                    ? "xl:grid-cols-[minmax(0,1.25fr)_380px] xl:items-end 2xl:grid-cols-[minmax(0,1.35fr)_420px]"
                    : "xl:grid-cols-1",
                )}
              >
                <div className="space-y-4">
                  <div className="max-w-5xl 2xl:max-w-6xl">
                    <h1
                      className={cn(
                        "text-4xl font-semibold tracking-[-0.06em] text-slate-950 md:text-5xl",
                        titleClassName,
                      )}
                    >
                      {title}
                    </h1>
                    {subtitle ? (
                      <p className={cn("mt-4 text-[15px] leading-8 text-slate-500", subtitleClassName)}>{subtitle}</p>
                    ) : null}
                  </div>
                </div>

                {showWorkspacePanel ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                    <div className="rounded-[26px] border border-black/[0.06] bg-white/70 p-5 shadow-[0_1px_0_rgba(255,255,255,0.9)_inset]">
                      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
                        Session
                      </div>
                      <div className="mt-2 text-base font-semibold tracking-[-0.03em] text-slate-950">
                        本地筛选控制台
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-500">
                        当前页面已接入统一评分卡体系，保留原有接口与业务行为。
                      </p>
                    </div>
                    <div className="rounded-[26px] border border-black/[0.06] bg-white/70 p-5 shadow-[0_1px_0_rgba(255,255,255,0.9)_inset] lg:hidden">
                      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
                        Navigation
                      </div>
                      <Button className="mt-4 w-full justify-center" variant="secondary" onClick={() => navigate("/hr/tasks")}>
                        返回导航
                      </Button>
                    </div>
                  </div>
                ) : null}
              </section>
            ) : null}

            {children}
          </motion.div>
        </main>
      </div>
    </div>
  );
}
