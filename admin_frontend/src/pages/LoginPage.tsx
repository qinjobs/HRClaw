import { useState } from "react";
import { ArrowRight, LockKeyhole, UserRound } from "lucide-react";

import { getBootstrap } from "@/lib/bootstrap";
import { postJson } from "@/lib/api";
import { BrandLogo } from "@/components/brand/brand-logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";

export function LoginPage() {
  const bootstrap = getBootstrap();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { pushToast } = useToast();

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await postJson("/api/login", { username: username.trim(), password });
      pushToast({ tone: "success", title: "登录成功", description: "正在进入后台工作台。" });
      window.location.href = bootstrap.nextPath || "/hr/tasks";
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "登录失败";
      setError(message);
      pushToast({ tone: "error", title: "登录失败", description: message });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="grid w-full max-w-6xl gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="overflow-hidden border-white/70 bg-slate-900 text-white shadow-xl shadow-slate-900/10">
          <CardHeader className="border-b border-white/10 bg-white/5 p-8">
            <BrandLogo variant="hero" className="drop-shadow-[0_18px_28px_rgba(0,0,0,0.16)]" />
            <CardDescription className="max-w-xl text-sm leading-7 text-slate-300">
              HR自己的龙虾，把推荐筛选、插件入库、批量导入、Workbench 和高阶检索统一到一套可交付的招聘后台里。
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 p-8 md:grid-cols-3">
            {[
              ["任务执行", "推荐流程与 BOSS 会话校验统一调度"],
              ["Workbench", "阶段、原因码、标签与跟进协同处理"],
              ["JD评分卡", "JD 评分卡生成与 Word/PDF 批量筛查"],
            ].map(([title, detail]) => (
              <div key={title} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-sm font-semibold text-white">{title}</div>
                <p className="mt-2 text-sm leading-6 text-slate-300">{detail}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-white/90 shadow-lg shadow-slate-900/5">
          <CardHeader className="p-8 pb-4">
            <CardTitle className="text-2xl">登录后台</CardTitle>
            <CardDescription className="text-sm leading-6">
              输入账号进入后台页面。初始管理员账号已预填，后续可在后台继续创建和维护 HR 用户。
            </CardDescription>
          </CardHeader>
          <CardContent className="p-8 pt-4">
            <form className="space-y-5" onSubmit={onSubmit}>
              <div className="space-y-2">
                <Label htmlFor="username">用户名</Label>
                <div className="relative">
                  <UserRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                  <Input
                    id="username"
                    className="pl-9"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">密码</Label>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                  <Input
                    id="password"
                    className="pl-9"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
                初始管理员：<span className="font-semibold text-slate-900">admin / admin</span>
              </div>
              {error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              ) : null}
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? "登录中..." : "进入后台"}
                <ArrowRight className="size-4" />
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
