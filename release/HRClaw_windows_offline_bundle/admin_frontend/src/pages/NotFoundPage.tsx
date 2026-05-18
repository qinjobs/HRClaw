import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md rounded-3xl border border-slate-200 bg-white px-8 py-10 text-center shadow-sm">
        <div className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Not Found</div>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-950">页面不存在</h1>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          当前路径没有对应的后台页面。你可以返回试点中心，或重新从导航进入其他模块。
        </p>
        <Button className="mt-6" asChild>
          <a href="/hr/trial">返回试点中心</a>
        </Button>
      </div>
    </div>
  );
}
