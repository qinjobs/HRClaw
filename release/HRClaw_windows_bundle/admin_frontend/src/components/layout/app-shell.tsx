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
  showPageTitle = true,
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
                        "text-[40px] font-semibold leading-[1.07] tracking-[-0.04em] text-[#1d1d1f] md:text-[56px]",
                        titleClassName,
                      )}
                    >
                      {title}
                    </h1>
                    {subtitle ? (
                      <p className={cn("mt-4 max-w-4xl text-[17px] leading-[1.47] tracking-[-0.022em] text-black/70", subtitleClassName)}>{subtitle}</p>
                    ) : null}
                  </div>
                </div>

                {showWorkspacePanel ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                    <div className="rounded-xl bg-black p-5 text-white">
                      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/48">
                        Session
                      </div>
                      <div className="mt-2 text-[21px] font-semibold leading-[1.19] tracking-[-0.03em] text-white">
                        本地筛选控制台
                      </div>
                      <p className="mt-2 text-[14px] leading-[1.43] text-white/72">
                        当前页面已接入统一评分卡体系，保留原有接口与业务行为。
                      </p>
                    </div>
                    <div className="rounded-xl bg-white p-5 lg:hidden">
                      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-black/42">
                        Navigation
                      </div>
                      <Button className="mt-4 w-full justify-center" variant="secondary" onClick={() => navigate("/hr/trial")}>
                        返回试点中心
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
