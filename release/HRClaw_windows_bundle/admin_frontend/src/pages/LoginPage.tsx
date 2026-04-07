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
      pushToast({ tone: "success", title: "登录成功", description: "正在进入试点中心。" });
      window.location.href = bootstrap.nextPath || "/hr/trial";
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "登录失败";
      setError(message);
      pushToast({ tone: "error", title: "登录失败", description: message });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f5f5f7] px-4 py-10">
      <div className="grid w-full max-w-6xl gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="overflow-hidden bg-black text-white shadow-none">
          <CardHeader className="border-b border-white/10 p-8">
            <BrandLogo variant="hero" className="drop-shadow-[0_18px_28px_rgba(0,0,0,0.16)]" />
            <CardDescription className="max-w-xl text-[17px] leading-[1.47] tracking-[-0.022em] text-white/72">
              HR自己的龙虾，把试点中心、推荐筛选、插件入库、批量导入、Workbench 和高阶检索统一到一套可交付的招聘后台里。
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 p-8 md:grid-cols-3">
            {[
              ["试点中心", "1 个岗位、1 个 HR、20-50 份简历的起点"],
              ["任务执行", "推荐流程与 BOSS 会话校验统一调度"],
              ["JD评分卡", "JD 评分卡生成与 Word/PDF 批量筛查"],
            ].map(([title, detail]) => (
              <div key={title} className="rounded-[12px] bg-white/[0.06] p-4">
                <div className="text-[21px] font-semibold leading-[1.19] text-white">{title}</div>
                <p className="mt-2 text-[14px] leading-[1.43] text-white/70">{detail}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-white shadow-[rgba(0,0,0,0.18)_3px_5px_30px_0px]">
          <CardHeader className="p-8 pb-4">
            <CardTitle className="text-[40px] leading-[1.1]">登录后台</CardTitle>
            <CardDescription className="text-[17px] leading-[1.47]">
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
              <div className="rounded-[12px] bg-[#f5f5f7] px-4 py-3 text-[15px] text-black/62">
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
