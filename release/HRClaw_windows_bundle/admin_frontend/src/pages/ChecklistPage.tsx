import { useEffect, useState } from "react";
import { CheckCheck, RefreshCcw } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { EmptyState } from "@/components/shared/empty-state";
import { PageSection } from "@/components/shared/page-section";
import { StatTile } from "@/components/shared/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { ScrollArea } from "@/components/ui/scroll-area";
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

          <ScrollArea className="hidden max-h-[680px] rounded-2xl border border-slate-200 md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>任务</TableHead>
                  <TableHead>Token 消耗</TableHead>
                  <TableHead>候选人</TableHead>
                  <TableHead>综合分</TableHead>
                  <TableHead>系统决策</TableHead>
                  <TableHead>打招呼</TableHead>
                  <TableHead>HR 复核</TableHead>
                  <TableHead>经验 / 学历 / 城市</TableHead>
                  <TableHead>岗位信息 / 搜索条件</TableHead>
                  <TableHead>模型提取</TableHead>
                  <TableHead>证据</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.candidate_id}>
                    <TableCell className="font-mono text-xs">
                      {item.task_id}
                      <div>状态：{item.task_status || "-"}</div>
                      <div>开始：{formatTime(item.task_started_at)}</div>
                      <div>结束：{formatTime(item.task_finished_at)}</div>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      总：{tokenNumber((item.task_token_usage || {}).total_tokens)}
                      <div>
                        输：{tokenNumber((item.task_token_usage || {}).prompt_tokens)} / 出：
                        {tokenNumber((item.task_token_usage || {}).completion_tokens)}
                      </div>
                      <div>调用：{tokenNumber((item.task_token_usage || {}).calls)}</div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-slate-950">{item.name || "-"}</div>
                      <div className="font-mono text-xs text-slate-500">{item.external_id || "-"}</div>
                    </TableCell>
                    <TableCell>{formatScore(item.total_score)}</TableCell>
                    <TableCell>
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
                    <TableCell>{item.greet_status || "-"}</TableCell>
                    <TableCell>
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
                    <TableCell>
                      {item.years_experience || "-"} 年 / {item.education_level || "-"} / {item.location || "-"}
                    </TableCell>
                    <TableCell>
                      <div>岗位：{item.job_name || item.job_id || "-"}</div>
                      <div>关键词：{(item.search_config || {}).keyword || "-"}</div>
                      <div>城市：{(item.search_config || {}).city || "-"}</div>
                    </TableCell>
                    <TableCell>
                      {item.gpt_extraction_used === true
                        ? "成功"
                        : item.gpt_extraction_used === false
                          ? "回退"
                          : "未知"}
                      {item.gpt_extraction_error ? (
                        <div className="mt-1 text-xs text-rose-600">{item.gpt_extraction_error}</div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        {item.screenshot_path ? (
                          <a
                            className="text-sm font-medium text-slate-700 underline-offset-4 hover:underline"
                            href={`/api/candidates/${item.candidate_id}/screenshot`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            简历截图
                          </a>
                        ) : (
                          <div>-</div>
                        )}
                        <a
                          className="text-sm font-medium text-slate-700 underline-offset-4 hover:underline"
                          href={`/api/candidates/${item.candidate_id}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          详情 JSON
                        </a>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>
    </AppShell>
  );
}
