import { useEffect, useState } from "react";
import { Braces, CheckCheck, FileImage, FileText, RefreshCcw } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { EmptyState } from "@/components/shared/empty-state";
import { PageSection } from "@/components/shared/page-section";
import { StatTile } from "@/components/shared/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getBootstrap } from "@/lib/bootstrap";
import { getJson, postJson } from "@/lib/api";
import { formatDecision, formatScore, formatTime } from "@/lib/format";
import type { ChecklistItem, JobOption } from "@/lib/types";
import { useToast } from "@/components/ui/toast";

interface ChecklistPayload {
  tasks: Array<Record<string, any>>;
  jobs: JobOption[];
  items: ChecklistItem[];
}

function tokenNumber(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : 0;
}

function formatAutoGreetRule(searchConfig?: Record<string, unknown> | null) {
  const threshold = searchConfig?.auto_greet_threshold;
  const parsed = Number(threshold);
  if (Number.isFinite(parsed) && parsed >= 0) {
    return `手动设置 ≥ ${parsed.toFixed(2)} 分`;
  }
  return "跟随评分卡 recommend 阈值";
}

function formatSearchConfigText(value: unknown) {
  const text = String(value ?? "").trim();
  return text || "-";
}

function EvidenceLink({
  href,
  label,
  hint,
  icon,
}: {
  href?: string | null;
  label: string;
  hint: string;
  icon: React.ReactNode;
}) {
  if (!href) {
    return (
      <div className="flex min-h-[64px] items-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-2 text-slate-400">
        <div className="flex size-9 items-center justify-center rounded-2xl bg-white text-slate-300 shadow-sm">
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium">{label}</div>
          <div className="text-xs">暂未生成</div>
        </div>
      </div>
    );
  }

  return (
    <a
      className="group flex min-h-[64px] items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-slate-700 transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      <div className="flex size-9 items-center justify-center rounded-2xl bg-slate-100 text-slate-600 transition group-hover:bg-slate-900 group-hover:text-white">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-semibold">{label}</div>
        <div className="text-xs text-slate-500">{hint}</div>
      </div>
    </a>
  );
}

export function ChecklistPage() {
  const bootstrap = getBootstrap();
  const { pushToast } = useToast();
  const [tasks, setTasks] = useState<Array<Record<string, any>>>([]);
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [taskId, setTaskId] = useState("");
  const [jobId, setJobId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [limit, setLimit] = useState("300");
  const [isLoading, setIsLoading] = useState(true);
  const [reviewingId, setReviewingId] = useState("");

  const loadChecklist = async () => {
    setIsLoading(true);
    const params = new URLSearchParams();
    if (taskId) params.set("task_id", taskId);
    if (jobId) params.set("job_id", jobId);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    params.set("limit", limit || "300");
    try {
      const data = await getJson<ChecklistPayload>(`/api/hr/checklist?${params.toString()}`);
      setTasks(data.tasks || []);
      setJobs(data.jobs || []);
      setItems(data.items || []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "加载失败";
      pushToast({ tone: "error", title: "Checklist 加载失败", description: message });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadChecklist();
  }, []);

  const markReviewed = async (candidateId: string) => {
    setReviewingId(candidateId);
    try {
      await postJson(`/api/candidates/${encodeURIComponent(candidateId)}/review`, {
        reviewer: "hr_ui",
        action: "approve",
        comment: "HR清单页面复核完成",
        final_decision: "reviewed_completed",
      });
      pushToast({ tone: "success", title: "复核已保存" });
      await loadChecklist();
    } catch (error) {
      const message = error instanceof Error ? error.message : "复核失败";
      pushToast({ tone: "error", title: "复核失败", description: message });
    } finally {
      setReviewingId("");
    }
  };

  const totalTokens = tasks.reduce(
    (sum, task) => sum + tokenNumber((task.token_usage || {}).total_tokens),
    0,
  );

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="Checklist"
      subtitle="HR 简历评分清单保留原有字段和动作，但重新梳理成更利于批量复核和稳定扫描的表格页。"
    >
      <div className="grid gap-4 md:grid-cols-3">
        <StatTile label="任务数" value={tasks.length} hint="当前筛选条件下返回的任务数量" />
        <StatTile label="候选人数" value={items.length} hint="按任务、岗位和日期过滤后的候选人" />
        <StatTile label="累计 Token" value={totalTokens} hint="来自任务 token_usage 的聚合值" />
      </div>

      <PageSection
        title="筛选条件"
        description="保留任务、岗位、日期和 limit 过滤，但补齐了 loading、empty 和 review action 的反馈。"
        actions={
          <Button variant="secondary" onClick={loadChecklist} disabled={isLoading}>
            <RefreshCcw className="size-4" />
            刷新
          </Button>
        }
      >
        <Card>
          <CardContent className="grid gap-4 p-6 md:grid-cols-5">
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">任务</label>
              <NativeSelect value={taskId} onChange={(event) => setTaskId(event.target.value)}>
                <option value="">全部任务</option>
                {tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.id} | {task.job_id} | {task.status}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">岗位</label>
              <NativeSelect value={jobId} onChange={(event) => setJobId(event.target.value)}>
                <option value="">全部岗位</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.name} ({job.id})
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">起始日期</label>
              <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">结束日期</label>
              <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">返回数量</label>
              <Input type="number" min="1" max="1000" value={limit} onChange={(event) => setLimit(event.target.value)} />
            </div>
          </CardContent>
        </Card>
      </PageSection>

      <Card>
        <CardHeader>
          <CardTitle>HR 简历评分清单</CardTitle>
        </CardHeader>
        <CardContent>
          {!items.length && !isLoading ? (
            <EmptyState title="暂无数据" description="当前筛选条件下还没有可复核的候选人。" />
          ) : null}

          <div className="md:hidden space-y-3">
            {items.map((item) => (
              <Card key={item.candidate_id} className="border-slate-200 shadow-none">
                <CardContent className="space-y-3 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-950">{item.name || "-"}</div>
                      <div className="text-xs text-slate-500">{item.external_id || "-"}</div>
                    </div>
                    <Badge
                      variant={
                        item.decision === "recommend"
                          ? "success"
                          : item.decision === "reject"
                            ? "danger"
                            : "warn"
                      }
                    >
                      {formatDecision(item.decision)}
                    </Badge>
                  </div>
                  <div className="text-sm text-slate-600">
                    {item.years_experience || "-"} 年 / {item.education_level || "-"} / {item.location || "-"}
                  </div>
                  <div className="text-sm text-slate-500">
                    岗位：{item.job_name || item.job_id || "-"} · 分数：{formatScore(item.total_score)}
                  </div>
                  <div className="text-sm text-slate-500">
                    自动打招呼：{formatAutoGreetRule(item.search_config)}
                  </div>
                  <Button
                    variant="secondary"
                    className="w-full"
                    disabled={!!item.review_action || reviewingId === item.candidate_id}
                    onClick={() => markReviewed(item.candidate_id)}
                  >
                    <CheckCheck className="size-4" />
                    {item.review_action ? "已复核" : reviewingId === item.candidate_id ? "复核中..." : "是否复核"}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="hidden rounded-2xl border border-slate-200 md:block">
            <div className="max-h-[680px] overflow-auto">
              <Table className="min-w-[1520px]">
                <TableHeader className="sticky top-0 z-10 bg-white shadow-[inset_0_-1px_0_rgba(15,23,42,0.08)]">
                <TableRow>
                  <TableHead className="min-w-[210px] whitespace-nowrap">任务</TableHead>
                  <TableHead className="min-w-[150px] whitespace-nowrap">Token 消耗</TableHead>
                  <TableHead className="min-w-[200px] whitespace-nowrap">候选人</TableHead>
                  <TableHead className="min-w-[96px] whitespace-nowrap">综合分</TableHead>
                  <TableHead className="min-w-[120px] whitespace-nowrap">系统决策</TableHead>
                  <TableHead className="min-w-[100px] whitespace-nowrap">打招呼</TableHead>
                  <TableHead className="min-w-[120px] whitespace-nowrap">HR 复核</TableHead>
                  <TableHead className="min-w-[170px] whitespace-nowrap">经验 / 学历 / 城市</TableHead>
                  <TableHead className="min-w-[280px] whitespace-nowrap">岗位信息 / 搜索条件</TableHead>
                  <TableHead className="min-w-[150px] whitespace-nowrap">模型提取</TableHead>
                  <TableHead className="min-w-[130px] whitespace-nowrap">证据</TableHead>
                </TableRow>
                </TableHeader>
                <TableBody>
                {items.map((item) => (
                  <TableRow key={item.candidate_id}>
                    <TableCell className="min-w-[210px] break-all font-mono text-xs leading-6">
                      {item.task_id}
                      <div>状态：{item.task_status || "-"}</div>
                      <div>开始：{formatTime(item.task_started_at)}</div>
                      <div>结束：{formatTime(item.task_finished_at)}</div>
                    </TableCell>
                    <TableCell className="min-w-[150px] font-mono text-xs leading-6">
                      总：{tokenNumber((item.task_token_usage || {}).total_tokens)}
                      <div>
                        输：{tokenNumber((item.task_token_usage || {}).prompt_tokens)} / 出：
                        {tokenNumber((item.task_token_usage || {}).completion_tokens)}
                      </div>
                      <div>调用：{tokenNumber((item.task_token_usage || {}).calls)}</div>
                    </TableCell>
                    <TableCell className="min-w-[200px]">
                      <div className="font-medium text-slate-950">{item.name || "-"}</div>
                      <div className="break-all font-mono text-xs text-slate-500">{item.external_id || "-"}</div>
                    </TableCell>
                    <TableCell className="min-w-[96px] whitespace-nowrap">{formatScore(item.total_score)}</TableCell>
                    <TableCell className="min-w-[120px] whitespace-nowrap">
                      <Badge
                        variant={
                          item.decision === "recommend"
                            ? "success"
                            : item.decision === "reject"
                              ? "danger"
                              : "warn"
                        }
                      >
                        {formatDecision(item.decision)}
                      </Badge>
                    </TableCell>
                    <TableCell className="min-w-[100px] whitespace-nowrap">{item.greet_status || "-"}</TableCell>
                    <TableCell className="min-w-[120px] whitespace-nowrap">
                      {item.review_action || item.final_decision ? (
                        <Badge variant="success">复核完成</Badge>
                      ) : (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={reviewingId === item.candidate_id}
                          onClick={() => markReviewed(item.candidate_id)}
                        >
                          {reviewingId === item.candidate_id ? "复核中..." : "是否复核"}
                        </Button>
                      )}
                    </TableCell>
                    <TableCell className="min-w-[170px] whitespace-nowrap">
                      {item.years_experience || "-"} 年 / {item.education_level || "-"} / {item.location || "-"}
                    </TableCell>
                    <TableCell className="min-w-[320px]">
                      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm leading-5 text-slate-700">
                        <div className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">岗位</div>
                          <div className="truncate text-slate-950">{item.job_name || item.job_id || "-"}</div>
                        </div>
                        <div className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">关键词</div>
                          <div className="truncate text-slate-950">{formatSearchConfigText(item.search_config?.keyword)}</div>
                        </div>
                        <div className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">城市</div>
                          <div className="truncate text-slate-950">{formatSearchConfigText(item.search_config?.city)}</div>
                        </div>
                        <div className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">自动打招呼</div>
                          <div className="truncate text-slate-950">{formatAutoGreetRule(item.search_config)}</div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="min-w-[150px] leading-6">
                      {item.gpt_extraction_used === true
                        ? "成功"
                        : item.gpt_extraction_used === false
                          ? "回退"
                          : "未知"}
                      {item.gpt_extraction_error ? (
                        <div className="mt-1 text-xs text-rose-600">{item.gpt_extraction_error}</div>
                        ) : null}
                    </TableCell>
                    <TableCell className="min-w-[260px]">
                      <div className="grid gap-2">
                        <EvidenceLink
                          href={
                            item.resume_full_screenshot_path || item.screenshot_path
                              ? `/api/candidates/${item.candidate_id}/screenshot`
                              : null
                          }
                          label="完整简历截图"
                          hint="查看长图归档"
                          icon={<FileImage className="size-4" />}
                        />
                        <EvidenceLink
                          href={item.resume_markdown_path ? `/api/candidates/${item.candidate_id}/resume-markdown` : null}
                          label="Markdown 简历"
                          hint="查看结构化文本"
                          icon={<FileText className="size-4" />}
                        />
                        <EvidenceLink
                          href={`/api/candidates/${item.candidate_id}`}
                          label="详情 JSON"
                          hint="查看原始记录"
                          icon={<Braces className="size-4" />}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
