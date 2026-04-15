import { useEffect, useState } from "react";
import { PlayCircle } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { StatTile } from "@/components/shared/stat-tile";
import { StatusBanner } from "@/components/shared/status-banner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getBootstrap } from "@/lib/bootstrap";
import { getJson, postJson } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import type { JobOption } from "@/lib/types";

function scorecardKindLabel(item: JobOption) {
  if (item.kind === "builtin_phase1") return "内置 JD评分卡";
  if (item.kind === "custom_phase2") return "自定义 JD评分卡";
  return "JD评分卡";
}

export function TasksPage() {
  const bootstrap = getBootstrap();
  const { pushToast } = useToast();
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [jobId, setJobId] = useState("");
  const [maxCandidates, setMaxCandidates] = useState("50");
  const [maxPages, setMaxPages] = useState("30");
  const [sortBy, setSortBy] = useState("active");
  const [keyword, setKeyword] = useState("");
  const [city, setCity] = useState("");
  const [autoGreetThreshold, setAutoGreetThreshold] = useState("");
  const [logs, setLogs] = useState<string[]>(["等待操作..."]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [runningTask, setRunningTask] = useState(false);

  const appendLog = (message: string) => {
    const timestamp = new Date().toLocaleString();
    setLogs((current) => [`[${timestamp}] ${message}`, ...current]);
  };

  useEffect(() => {
    const loadJobs = async () => {
      try {
        const data = await getJson<{ items: JobOption[] }>("/api/scoring-targets");
        setJobs(data.items || []);
        setJobId(data.items?.[0]?.id || "");
      } catch (error) {
        const message = error instanceof Error ? error.message : "加载岗位失败";
        appendLog(`加载岗位失败：${message}`);
      } finally {
        setLoadingJobs(false);
      }
    };
    void loadJobs();
  }, []);

  useEffect(() => {
    const selectedJob = jobs.find((item) => item.id === jobId) || jobs[0];
    const scorecard = selectedJob?.scorecard as Record<string, any> | undefined;
    const filters = scorecard?.filters as Record<string, unknown> | undefined;
    setKeyword(selectedJob?.name || "");
    setCity(String(filters?.location || "").trim());
  }, [jobId, jobs]);

  const createAndRun = async () => {
    setRunningTask(true);
    appendLog("开始创建并执行 Recommend 任务，请先在当前 Chrome 中手动登录 BOSS，然后直接采集当前页面。");
    try {
      const payload = {
        job_id: jobId,
        max_candidates: Number(maxCandidates || 50),
        max_pages: Number(maxPages || 30),
        sort_by: sortBy,
        search_config: {
          ...(keyword.trim() ? { keyword: keyword.trim() } : {}),
          ...(city.trim() ? { city: city.trim() } : {}),
          ...(autoGreetThreshold.trim() === ""
            ? {}
            : { auto_greet_threshold: Number(autoGreetThreshold) }),
        },
      };
      const data = await postJson<{ task_id?: string; result?: { processed?: unknown[] } }>(
        "/api/recommend/run",
        payload,
      );
      appendLog(`任务完成：task_id=${data.task_id || "-"}，处理=${data.result?.processed?.length || 0}`);
      pushToast({ tone: "success", title: "任务执行完成", description: `任务 ID：${data.task_id || "-"}` });
      if (data.task_id) {
        window.location.href = `/hr/checklist?task_id=${encodeURIComponent(data.task_id)}`;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "执行失败";
      appendLog(`执行失败：${message}`);
      pushToast({ tone: "error", title: "任务执行失败", description: message });
    } finally {
      setRunningTask(false);
    }
  };

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="任务执行"
      subtitle="执行顺序已调整为：HR 先在已安装插件的 Chrome 中手动登录 BOSS，然后直接在登录好的浏览器里采集当前页面，再执行 recommend 采集、评分和结果回填。分数达到评分卡 recommend 阈值后，会自动点击打招呼。"
    >
      <div className="grid gap-4 md:grid-cols-3">
        <StatTile label="默认流程" value="Recommend" hint="手动登录 → 当前页采集 → 打分 → 清单回写" />
        <StatTile label="当前模式" value={sortBy === "active" ? "活跃优先" : "最新优先"} hint="排序只影响候选人扫描顺序" />
        <StatTile label="后台入口" value="5 个模块" hint="任务执行、推荐处理台、Checklist、搜索、JD评分卡" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(380px,0.9fr)]">
        <Card className="overflow-hidden bg-black text-white shadow-none">
          <CardHeader>
            <CardTitle className="text-white">创建并执行任务</CardTitle>
            <CardDescription className="text-white/72">
              保留原有业务逻辑和接口，但把配置结构、状态反馈和主次按钮层级整理成更稳定的后台操作流。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 text-white">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="jobId">JD评分卡</Label>
                <NativeSelect
                  className="border-white/14 bg-white/[0.08] text-white"
                  iconClassName="text-white/46"
                  id="jobId"
                  value={jobId}
                  disabled={loadingJobs}
                  onChange={(event) => setJobId(event.target.value)}
                >
                  {jobs.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {scorecardKindLabel(item)}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="maxCandidates">最大人数</Label>
                <Input
                  className="border-white/14 bg-white/[0.08] text-white placeholder:text-white/35"
                  id="maxCandidates"
                  type="number"
                  min="1"
                  max="200"
                  value={maxCandidates}
                  onChange={(event) => setMaxCandidates(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="maxPages">最大分页</Label>
                <Input
                  className="border-white/14 bg-white/[0.08] text-white placeholder:text-white/35"
                  id="maxPages"
                  type="number"
                  min="1"
                  max="100"
                  value={maxPages}
                  onChange={(event) => setMaxPages(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="sortBy">排序</Label>
                <NativeSelect
                  className="border-white/14 bg-white/[0.08] text-white"
                  iconClassName="text-white/46"
                  id="sortBy"
                  value={sortBy}
                  onChange={(event) => setSortBy(event.target.value)}
                >
                  <option value="active">活跃优先</option>
                  <option value="recent">最新优先</option>
                </NativeSelect>
              </div>
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="keyword">关键词</Label>
                <Input
                  className="border-white/14 bg-white/[0.08] text-white placeholder:text-white/35"
                  id="keyword"
                  placeholder="默认跟随评分卡名称"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="city">城市</Label>
                <Input
                  className="border-white/14 bg-white/[0.08] text-white placeholder:text-white/35"
                  id="city"
                  placeholder="默认跟随评分卡地点"
                  value={city}
                  onChange={(event) => setCity(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-white/72" htmlFor="autoGreetThreshold">自动打招呼阈值</Label>
                <Input
                  className="border-white/14 bg-white/[0.08] text-white placeholder:text-white/35"
                  id="autoGreetThreshold"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  placeholder="留空则使用评分卡 recommend 阈值"
                  value={autoGreetThreshold}
                  onChange={(event) => setAutoGreetThreshold(event.target.value)}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <StatusBanner
                tone="default"
                title="手动登录"
                description="系统不再拉起单独的 BOSS 登录浏览器，也不再依赖保存会话。请在已安装插件的 Chrome 中手动登录 BOSS，然后直接在登录好的浏览器里采集当前页面。"
              />
              <StatusBanner
                tone="default"
                title="执行结果"
                description="执行完成后会自动跳转到 Checklist，并保留 task_id 方便继续复核。"
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <Button onClick={createAndRun} disabled={runningTask || !jobId}>
                <PlayCircle className="size-4" />
                {runningTask ? "执行中..." : "创建并执行 Recommend 任务"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>执行日志</CardTitle>
              <CardDescription>保留原始操作反馈，但改成更易扫读的日志面板。</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[320px] rounded-2xl border border-slate-200 bg-slate-950 p-4">
                <div className="space-y-2 font-mono text-xs leading-6 text-slate-300">
                  {logs.map((log) => (
                    <div key={log}>{log}</div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
