import { useEffect, useState } from "react";
import { PlayCircle, RotateCcw, Save } from "lucide-react";

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
import { ApiError, getJson, postJson } from "@/lib/api";
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
  const [logs, setLogs] = useState<string[]>(["等待操作..."]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [resettingSession, setResettingSession] = useState(false);
  const [savingSession, setSavingSession] = useState(false);
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

  const resetSessionAndRelogin = async () => {
    setResettingSession(true);
    appendLog("开始清空本地已保存的 BOSS 会话...");
    try {
      const data = await postJson<{ message?: string }>("/api/boss/session/reset", {});
      appendLog(data.message || "已清空本地会话。请先在 Chrome 的 BOSS 页面手动登录，并刷新一次 BOSS 页面让插件重新同步。");
      pushToast({
        tone: "info",
        title: "已清空本地会话",
        description: data.message || "请在已安装插件的 Chrome 中手动登录 BOSS，并刷新一次 BOSS 页面。",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "清空旧会话失败";
      appendLog(`清空旧会话失败：${message}`);
      pushToast({ tone: "error", title: "清空旧会话失败", description: message });
    } finally {
      setResettingSession(false);
    }
  };

  const saveSessionOnly = async () => {
    setSavingSession(true);
    appendLog("开始检查当前 Chrome 已同步的 BOSS 会话。如果你刚手动登录 BOSS，请先刷新一次 BOSS 页面，让插件完成同步。");
    try {
      const data = await postJson<{ login_detected: boolean; reason?: string }>("/api/boss/session/save", {});
      appendLog(`会话检测通过并已保存：login_detected=${data.login_detected}，reason=${data.reason || "-"}`);
      pushToast({ tone: "success", title: "BOSS 会话已确认" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "会话保存失败";
      appendLog(`会话保存失败：${message}`);
      if (error instanceof ApiError && typeof error.payload === "object" && error.payload && "summary" in error.payload) {
        pushToast({ tone: "info", title: "请先在 Chrome 中手动登录 BOSS", description: message });
      } else {
        pushToast({ tone: "error", title: "会话保存失败", description: message });
      }
    } finally {
      setSavingSession(false);
    }
  };

  const createAndRun = async () => {
    setRunningTask(true);
    appendLog("开始创建并执行 Recommend 任务，系统会先校验已保存的 BOSS 会话...");
    try {
      const payload = {
        job_id: jobId,
        max_candidates: Number(maxCandidates || 50),
        max_pages: Number(maxPages || 30),
        sort_by: sortBy,
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
      subtitle="执行顺序已调整为：HR 先在已安装插件的 Chrome 中手动登录 BOSS，插件同步当前会话，系统确认后再执行 recommend 采集、评分和结果回填。"
    >
      <div className="grid gap-4 md:grid-cols-3">
        <StatTile label="默认流程" value="Recommend" hint="会话校验 → 推荐采集 → 打分 → 清单回写" />
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
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <StatusBanner
                tone="default"
                title="会话检查"
                description="系统不再拉起单独的 BOSS 登录浏览器。请在已安装插件的 Chrome 中手动登录 BOSS，并刷新一次 BOSS 页面，让插件把当前会话同步到本地系统。"
              />
              <StatusBanner
                tone="default"
                title="执行结果"
                description="执行完成后会自动跳转到 Checklist，并保留 task_id 方便继续复核。"
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="ghost" onClick={resetSessionAndRelogin} disabled={resettingSession || savingSession}>
                <RotateCcw className="size-4" />
                {resettingSession ? "清空中..." : "清空已保存会话"}
              </Button>
              <Button variant="secondary" onClick={saveSessionOnly} disabled={savingSession || resettingSession}>
                <Save className="size-4" />
                {savingSession ? "检查中..." : "检查已同步的 BOSS 会话"}
              </Button>
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
