import { useEffect, useState, useTransition } from "react";
import { LoaderCircle, Plus, RefreshCcw, Save } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { EmptyState } from "@/components/shared/empty-state";
import { PageSection } from "@/components/shared/page-section";
import { StatTile } from "@/components/shared/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { candidateActionStatusLabels, finalDecisionLabels, reasonCodeLabels, stageLabels } from "@/lib/constants";
import { getJson, postJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import { compactText, formatDecision, formatScore, formatStage, formatTime, safeList, toDateTimeLocal } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import type { JobOption, WorkbenchDetail, WorkbenchItem } from "@/lib/types";

const reviewActionLabels: Record<string, string> = {
  approve: "通过复核",
  reject: "复核淘汰",
  hold: "暂缓处理",
  mark_reviewed: "已人工复核",
};

const confirmActionLabels: Record<string, string> = {
  send_greeting: "确认打招呼",
  download_resume: "确认下载简历",
  advance_pipeline: "确认推进流程",
};

const candidateActionTypeLabels: Record<string, string> = {
  send_greeting: "打招呼",
  download_resume: "下载简历",
  advance_pipeline: "推进流程",
};

const quickActions = {
  toContact: { current_stage: "to_contact", final_decision: "recommend", reason_code: "skills_match", review_action: "approve" },
  needInfo: { current_stage: "needs_followup", final_decision: "review", reason_code: "resume_incomplete", review_action: "hold" },
  keepPool: { current_stage: "talent_pool", final_decision: "talent_pool", reason_code: "reusable_pool", reusable_flag: true },
  invited: { current_stage: "interview_invited", final_decision: "recommend", reason_code: "candidate_positive", review_action: "approve" },
  reject: { current_stage: "rejected", final_decision: "reject", reason_code: "skills_gap", review_action: "reject" },
  block: { current_stage: "do_not_contact", final_decision: "reject", reason_code: "do_not_contact", do_not_contact: true, review_action: "reject" },
} as const;

type QuickActionPreset = {
  current_stage: string;
  final_decision: string;
  reason_code: string;
  review_action?: string;
  reusable_flag?: boolean;
  do_not_contact?: boolean;
};

type TriState = "" | "true" | "false";

interface WorkbenchFilters {
  taskId: string;
  jobId: string;
  source: string;
  keyword: string;
  stage: string;
  decision: string;
  greetStatus: string;
  owner: string;
  limit: string;
  reusableOnly: boolean;
  needsFollowUp: boolean;
  unreviewedOnly: boolean;
  manualStageLocked: TriState;
  doNotContact: TriState;
}

interface DetailFormState {
  owner: string;
  current_stage: string;
  reason_code: string;
  final_decision: string;
  last_contacted_at: string;
  last_contact_result: string;
  next_follow_up_at: string;
  talent_pool_status: string;
  reason_notes: string;
  reusable_flag: boolean;
  do_not_contact: boolean;
}

const defaultFilters: WorkbenchFilters = {
  taskId: "",
  jobId: "",
  source: "",
  keyword: "",
  stage: "",
  decision: "",
  greetStatus: "",
  owner: "",
  limit: "120",
  reusableOnly: false,
  needsFollowUp: false,
  unreviewedOnly: false,
  manualStageLocked: "",
  doNotContact: "",
};

const defaultDetailForm: DetailFormState = {
  owner: "",
  current_stage: "new",
  reason_code: "",
  final_decision: "",
  last_contacted_at: "",
  last_contact_result: "",
  next_follow_up_at: "",
  talent_pool_status: "",
  reason_notes: "",
  reusable_flag: false,
  do_not_contact: false,
};

function joinHumanParts(parts: Array<string | null | undefined | false>) {
  return parts.filter(Boolean).join("；");
}

function timelineEventTitle(entry: Record<string, any>) {
  const eventType = String(entry.event_type || "");
  if (eventType === "tag_added") return "已添加标签";
  if (eventType === "stage_updated") return "处理状态已更新";
  if (eventType === "review_action") return "已保存复核结果";
  if (eventType === "follow_up_scheduled") return "已设置跟进计划";
  if (eventType === "confirm_action") return "已确认系统动作";
  if (eventType === "seeded") return "系统初始化记录";
  return "候选人状态更新";
}

function timelineEventSummary(entry: Record<string, any>) {
  const eventType = String(entry.event_type || "");
  const payload = entry.event_payload || {};
  if (eventType === "tag_added") {
    return joinHumanParts([
      payload.tag ? `添加标签：${payload.tag}` : "",
      payload.tag_type && payload.tag_type !== "manual" ? `类型：${payload.tag_type}` : "",
    ]) || "已新增候选人标签。";
  }
  if (eventType === "stage_updated") {
    return (
      joinHumanParts([
        payload.current_stage ? `阶段变更为：${stageLabels[payload.current_stage] || payload.current_stage}` : "",
        payload.reason_code ? `原因：${reasonCodeLabels[payload.reason_code] || payload.reason_code}` : "",
        payload.final_decision ? `结论：${finalDecisionLabels[payload.final_decision] || payload.final_decision}` : "",
        payload.last_contact_result ? `沟通结果：${payload.last_contact_result}` : "",
        payload.next_follow_up_at ? `下次跟进：${payload.next_follow_up_at}` : "",
        payload.reusable_flag ? "已标记为可复用" : "",
        payload.do_not_contact ? "已标记为不再联系" : "",
        payload.reason_notes ? `备注：${payload.reason_notes}` : "",
      ]) || "已更新候选人处理状态。"
    );
  }
  if (eventType === "review_action") {
    return (
      joinHumanParts([
        payload.action ? `复核动作：${reviewActionLabels[payload.action] || payload.action}` : "",
        payload.final_decision ? `复核结论：${finalDecisionLabels[payload.final_decision] || payload.final_decision}` : "",
        payload.comment ? `备注：${payload.comment}` : "",
      ]) || "已记录 HR 复核结果。"
    );
  }
  if (eventType === "follow_up_scheduled") {
    return (
      joinHumanParts([
        payload.next_follow_up_at ? `下次跟进时间：${payload.next_follow_up_at}` : "",
        payload.last_contact_result ? `当前沟通结果：${payload.last_contact_result}` : "",
        payload.comment ? `备注：${payload.comment}` : "",
      ]) || "已保存跟进计划。"
    );
  }
  if (eventType === "confirm_action") {
    return (
      joinHumanParts([
        payload.action ? `确认动作：${confirmActionLabels[payload.action] || payload.action}` : "",
        payload.final_decision ? `处理结果：${finalDecisionLabels[payload.final_decision] || payload.final_decision}` : "",
        payload.comment ? `备注：${payload.comment}` : "",
      ]) || "已确认系统动作。"
    );
  }
  const values = Object.values(payload || {}).map((value) => String(value || "").trim()).filter(Boolean);
  return values.length ? values.join("；") : "已记录一条候选人操作。";
}

function reviewSummary(review?: Record<string, any>) {
  if (!review) return "暂无";
  return (
    joinHumanParts([
      review.action ? reviewActionLabels[review.action] || review.action : "",
      review.final_decision ? finalDecisionLabels[review.final_decision] || review.final_decision : "",
      review.reviewer ? `操作人：${review.reviewer}` : "",
    ]) || "已保存复核结果"
  );
}

function actionSummary(action?: Record<string, any>) {
  if (!action) return "";
  const detail = action.detail || {};
  return joinHumanParts([
    action.action_type ? candidateActionTypeLabels[action.action_type] || action.action_type : "",
    action.status ? candidateActionStatusLabels[action.status] || action.status : "",
    detail.reason ? `原因：${detail.reason}` : "",
  ]);
}

function buildQuery(filters: WorkbenchFilters) {
  const params = new URLSearchParams();
  if (filters.taskId) params.set("task_id", filters.taskId);
  if (filters.jobId) params.set("job_id", filters.jobId);
  if (filters.source) params.set("source", filters.source);
  if (filters.keyword.trim()) params.set("keyword", filters.keyword.trim());
  if (filters.stage) params.set("stage", filters.stage);
  if (filters.decision) params.set("decision", filters.decision);
  if (filters.greetStatus) params.set("greet_status", filters.greetStatus);
  if (filters.owner.trim()) params.set("owner", filters.owner.trim());
  if (filters.limit) params.set("limit", filters.limit);
  if (filters.reusableOnly) params.set("reusable_only", "true");
  if (filters.needsFollowUp) params.set("needs_follow_up", "true");
  if (filters.unreviewedOnly) params.set("unreviewed_only", "true");
  if (filters.manualStageLocked) params.set("manual_stage_locked", filters.manualStageLocked);
  if (filters.doNotContact) params.set("do_not_contact", filters.doNotContact);
  return params.toString();
}

function formatThresholdLabel(value: unknown) {
  const parsed = Number(value);
  if (Number.isFinite(parsed) && parsed >= 0) {
    return `>= ${parsed.toFixed(2)} 分`;
  }
  return "跟随评分卡 recommend 阈值";
}

export function WorkbenchPage() {
  const bootstrap = getBootstrap();
  const { pushToast } = useToast();
  const [filters, setFilters] = useState<WorkbenchFilters>(defaultFilters);
  const [tasks, setTasks] = useState<Array<Record<string, any>>>([]);
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [stageOptions, setStageOptions] = useState<string[]>([]);
  const [reasonCodeOptions, setReasonCodeOptions] = useState<string[]>([]);
  const [finalDecisionOptions, setFinalDecisionOptions] = useState<string[]>([]);
  const [items, setItems] = useState<WorkbenchItem[]>([]);
  const [detail, setDetail] = useState<WorkbenchDetail | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [detailForm, setDetailForm] = useState<DetailFormState>(defaultDetailForm);
  const [tagInput, setTagInput] = useState("");
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isPending, startTransition] = useTransition();

  const hydrateForm = (payload: WorkbenchDetail) => {
    const state = payload.pipeline_state || {};
    setDetailForm({
      owner: String(state.owner || ""),
      current_stage: String(state.current_stage || "new"),
      reason_code: String(state.reason_code || ""),
      final_decision: String(state.final_decision || ""),
      last_contacted_at: toDateTimeLocal(state.last_contacted_at),
      last_contact_result: String(state.last_contact_result || ""),
      next_follow_up_at: toDateTimeLocal(state.next_follow_up_at),
      talent_pool_status: String(state.talent_pool_status || ""),
      reason_notes: String(state.reason_notes || ""),
      reusable_flag: Boolean(state.reusable_flag),
      do_not_contact: Boolean(state.do_not_contact),
    });
  };

  const loadCandidate = async (candidateId: string) => {
    setSelectedCandidateId(candidateId);
    setLoadingDetail(true);
    try {
      const data = await getJson<WorkbenchDetail>(`/api/hr/workbench/candidates/${encodeURIComponent(candidateId)}`);
      startTransition(() => {
        setDetail(data);
        hydrateForm(data);
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "候选人加载失败";
      pushToast({ tone: "error", title: "加载候选人失败", description: message });
    } finally {
      setLoadingDetail(false);
    }
  };

  const loadWorkbench = async (resetSelection = true) => {
    setLoadingQueue(true);
    try {
      const data = await getJson<any>(`/api/hr/workbench?${buildQuery(filters)}`);
      startTransition(() => {
        setItems(data.items || []);
        setTasks(data.tasks || []);
        setJobs(data.jobs || []);
        setStageOptions(data.stage_options || []);
        setReasonCodeOptions(data.reason_code_options || []);
        setFinalDecisionOptions(data.final_decision_options || []);
      });
      const nextCandidateId =
        !resetSelection && selectedCandidateId && (data.items || []).some((item: WorkbenchItem) => item.candidate_id === selectedCandidateId)
          ? selectedCandidateId
          : data.items?.[0]?.candidate_id || "";
      if (nextCandidateId) {
        await loadCandidate(nextCandidateId);
      } else {
        setSelectedCandidateId("");
        setDetail(null);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Workbench 加载失败";
      pushToast({ tone: "error", title: "加载失败", description: message });
    } finally {
      setLoadingQueue(false);
    }
  };

  useEffect(() => {
    void loadWorkbench(true);
  }, []);

  const updateFilter = <K extends keyof WorkbenchFilters>(key: K, value: WorkbenchFilters[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const saveStage = async (preset?: Partial<QuickActionPreset>) => {
    if (!selectedCandidateId) return;
    setSaving(true);
    try {
      await postJson(`/api/candidates/${encodeURIComponent(selectedCandidateId)}/stage`, {
        operator: "hr_ui",
        owner: detailForm.owner.trim() || null,
        current_stage: preset?.current_stage || detailForm.current_stage,
        reason_code: preset?.reason_code || detailForm.reason_code || null,
        reason_notes: detailForm.reason_notes.trim() || null,
        final_decision: preset?.final_decision || detailForm.final_decision || null,
        last_contacted_at: detailForm.last_contacted_at || null,
        last_contact_result: detailForm.last_contact_result.trim() || null,
        next_follow_up_at: detailForm.next_follow_up_at || null,
        reusable_flag: preset?.reusable_flag ?? detailForm.reusable_flag,
        do_not_contact: preset?.do_not_contact ?? detailForm.do_not_contact,
        talent_pool_status: detailForm.talent_pool_status.trim() || null,
        review_action: preset?.review_action || null,
      });
      pushToast({ tone: "success", title: "处理结果已保存" });
      await loadWorkbench(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      pushToast({ tone: "error", title: "保存失败", description: message });
    } finally {
      setSaving(false);
    }
  };

  const saveFollowUp = async () => {
    if (!selectedCandidateId) return;
    setSaving(true);
    try {
      await postJson(`/api/candidates/${encodeURIComponent(selectedCandidateId)}/follow-up`, {
        operator: "hr_ui",
        next_follow_up_at: detailForm.next_follow_up_at || null,
        last_contact_result: detailForm.last_contact_result.trim() || null,
        comment: detailForm.reason_notes.trim() || null,
      });
      pushToast({ tone: "success", title: "跟进计划已保存" });
      await loadWorkbench(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      pushToast({ tone: "error", title: "保存失败", description: message });
    } finally {
      setSaving(false);
    }
  };

  const addTag = async () => {
    if (!selectedCandidateId || !tagInput.trim()) return;
    try {
      await postJson(`/api/candidates/${encodeURIComponent(selectedCandidateId)}/tags`, {
        tag: tagInput.trim(),
        created_by: "hr_ui",
        tag_type: "manual",
      });
      setTagInput("");
      pushToast({ tone: "success", title: "标签已添加" });
      await loadWorkbench(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "添加标签失败";
      pushToast({ tone: "error", title: "添加标签失败", description: message });
    }
  };

  const decisionCounts = {
    recommend: items.filter((item) => item.decision === "recommend").length,
    review: items.filter((item) => item.decision === "review").length,
    reject: items.filter((item) => item.decision === "reject").length,
  };

  const detailCandidate = detail?.candidate || {};
  const detailScore = detail?.score || {};
  const detailSnapshot = detail?.snapshot || {};
  const detailTask = detail?.task || {};
  const detailJob = detail?.job || {};
  const detailReviews = detail?.reviews || detail?.review_actions || [];
  const detailActions = detail?.actions || [];
  const detailTimeline = detail?.timeline || [];
  const detailTags = detail?.tags || [];
  const selectedQueueItem = items.find((entry) => entry.candidate_id === selectedCandidateId) || null;
  const detailReasons = safeList(
    detailScore.review_reasons?.length ? detailScore.review_reasons : detailScore.hard_filter_fail_reasons,
  );
  const latestGreetAction = [...detailActions]
    .reverse()
    .find((entry) => entry.action_type === "send_greeting");
  const latestGreetDetail =
    latestGreetAction && latestGreetAction.detail && typeof latestGreetAction.detail === "object"
      ? latestGreetAction.detail
      : null;
  const latestGreetStatus = String(latestGreetAction?.status || selectedQueueItem?.greet_status || "");
  const latestGreetThreshold = latestGreetDetail?.threshold;
  const latestGreetScore = latestGreetDetail?.score ?? detailScore.total_score;
  const latestGreetReason = latestGreetDetail?.reason;

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="推荐处理台"
      subtitle="集中处理推荐牛人结果，把阶段、原因码、标签和跟进动作沉淀在一个页面里。数据、字段与保存接口保持原样。"
    >
      <div className="grid gap-4 md:grid-cols-4">
        <StatTile label="候选人数" value={items.length} hint="当前筛选结果中的候选人数" />
        <StatTile label="建议沟通" value={decisionCounts.recommend} hint="系统决策 recommend" />
        <StatTile label="继续复核" value={decisionCounts.review} hint="系统决策 review" />
        <StatTile label="暂不沟通" value={decisionCounts.reject} hint="系统决策 reject" />
      </div>

      <PageSection
        title="筛选与队列"
        description="保留所有过滤条件，但把使用频率更高的字段前置，复选条件集中到底部，减轻横向扫描压力。"
        actions={
          <Button variant="secondary" onClick={() => loadWorkbench(false)} disabled={loadingQueue}>
            <RefreshCcw className="size-4" />
            刷新队列
          </Button>
        }
      >
        <Card>
          <CardContent className="grid gap-4 p-6 lg:grid-cols-4 xl:grid-cols-6">
            <div className="space-y-2 xl:col-span-2">
              <Label htmlFor="keyword">关键词</Label>
              <Input
                id="keyword"
                placeholder="姓名 / 公司 / 职位 / external_id"
                value={filters.keyword}
                onChange={(event) => updateFilter("keyword", event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void loadWorkbench(true);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label>任务</Label>
              <NativeSelect value={filters.taskId} onChange={(event) => updateFilter("taskId", event.target.value)}>
                <option value="">全部任务</option>
                {tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.id} | {task.job_id} | {task.status}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>岗位</Label>
              <NativeSelect value={filters.jobId} onChange={(event) => updateFilter("jobId", event.target.value)}>
                <option value="">全部岗位</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.name} ({job.id})
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>来源</Label>
              <NativeSelect value={filters.source} onChange={(event) => updateFilter("source", event.target.value)}>
                <option value="">全部来源</option>
                <option value="boss_extension">插件入库</option>
                <option value="pipeline">任务采集</option>
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>当前阶段</Label>
              <NativeSelect value={filters.stage} onChange={(event) => updateFilter("stage", event.target.value)}>
                <option value="">全部阶段</option>
                {stageOptions.map((stage) => (
                  <option key={stage} value={stage}>
                    {formatStage(stage)}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>系统决策</Label>
              <NativeSelect value={filters.decision} onChange={(event) => updateFilter("decision", event.target.value)}>
                <option value="">全部决策</option>
                <option value="recommend">建议沟通</option>
                <option value="review">继续复核</option>
                <option value="reject">暂不沟通</option>
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>打招呼状态</Label>
              <NativeSelect value={filters.greetStatus} onChange={(event) => updateFilter("greetStatus", event.target.value)}>
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="skipped">已跳过</option>
                <option value="failed">失败</option>
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>Owner</Label>
              <Input value={filters.owner} placeholder="hr_1 / Lisa" onChange={(event) => updateFilter("owner", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>返回数量</Label>
              <Input type="number" min="1" max="500" value={filters.limit} onChange={(event) => updateFilter("limit", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>人工接管</Label>
              <NativeSelect value={filters.manualStageLocked} onChange={(event) => updateFilter("manualStageLocked", event.target.value as TriState)}>
                <option value="">全部</option>
                <option value="true">只看人工接管</option>
                <option value="false">只看未接管</option>
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label>不再联系</Label>
              <NativeSelect value={filters.doNotContact} onChange={(event) => updateFilter("doNotContact", event.target.value as TriState)}>
                <option value="">全部</option>
                <option value="true">仅不再联系</option>
                <option value="false">排除不再联系</option>
              </NativeSelect>
            </div>
            <div className="flex flex-wrap items-end gap-4 xl:col-span-6">
              <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={filters.reusableOnly} onChange={(event) => updateFilter("reusableOnly", event.target.checked)} />
                只看可复用
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={filters.needsFollowUp} onChange={(event) => updateFilter("needsFollowUp", event.target.checked)} />
                只看待跟进
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={filters.unreviewedOnly} onChange={(event) => updateFilter("unreviewedOnly", event.target.checked)} />
                只看未复核
              </label>
            </div>
          </CardContent>
        </Card>
      </PageSection>

      <div className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>候选人队列</CardTitle>
            <CardDescription>左侧保持高密度列表，右侧承接详情、快捷动作和处理表单。</CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[720px] pr-2">
              <div className="space-y-3">
                {loadingQueue ? (
                  <div className="flex items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 px-4 py-12 text-sm text-slate-500">
                    <LoaderCircle className="mr-2 size-4 animate-spin" />
                    正在加载队列...
                  </div>
                ) : !items.length ? (
                  <EmptyState title="暂无候选人" description="当前筛选条件下没有可处理的推荐结果。" />
                ) : (
                  items.map((item) => {
                    const candidateState = item.pipeline_state || {};
                    const reasons = safeList(
                      item.review_reasons?.length ? item.review_reasons : item.hard_filter_fail_reasons,
                    );
                    const stage = String(candidateState.current_stage || "new");
                    return (
                      <button
                        key={item.candidate_id}
                        type="button"
                        onClick={() => void loadCandidate(item.candidate_id)}
                        className={`w-full rounded-3xl border p-4 text-left transition-colors ${
                          selectedCandidateId === item.candidate_id
                            ? "border-slate-900 bg-slate-900 text-white"
                            : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-base font-semibold">{item.name || "未命名候选人"}</div>
                            <div className={`mt-1 text-sm ${selectedCandidateId === item.candidate_id ? "text-slate-300" : "text-slate-500"}`}>
                              {item.current_company || "-"} · {item.current_title || "-"}
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-xl font-semibold">{formatScore(item.total_score)}</div>
                            <div className={`text-xs ${selectedCandidateId === item.candidate_id ? "text-slate-300" : "text-slate-400"}`}>分</div>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge variant={selectedCandidateId === item.candidate_id ? "neutral" : "default"}>{formatStage(stage)}</Badge>
                          <Badge variant={selectedCandidateId === item.candidate_id ? "neutral" : "info"}>
                            {item.source === "boss_extension" ? "插件入库" : "任务采集"}
                          </Badge>
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
                        <p className={`mt-3 text-sm leading-6 ${selectedCandidateId === item.candidate_id ? "text-slate-200" : "text-slate-500"}`}>
                          {compactText(reasons.join("；") || item.raw_summary || "等待查看详情", 120)}
                        </p>
                      </button>
                    );
                  })
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <div className="space-y-6">
          {!selectedCandidateId || !detail ? (
            <EmptyState title="请选择候选人" description="从左侧队列中选择一位候选人，右侧会展示系统判断、证据、标签、时间线和处理动作。" />
          ) : (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>{detailCandidate.name || "未命名候选人"}</CardTitle>
                  <CardDescription>先看系统结论，再决定是否沟通、沉淀人才库或继续跟进。</CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  {loadingDetail ? (
                    <div className="flex items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 px-4 py-12 text-sm text-slate-500">
                      <LoaderCircle className="mr-2 size-4 animate-spin" />
                      正在加载候选人详情...
                    </div>
                  ) : null}
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="text-xs uppercase tracking-[0.08em] text-slate-400">当前职位</div>
                      <div className="mt-2 font-medium text-slate-950">{detailCandidate.current_title || "-"}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="text-xs uppercase tracking-[0.08em] text-slate-400">当前公司</div>
                      <div className="mt-2 font-medium text-slate-950">{detailCandidate.current_company || "-"}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="text-xs uppercase tracking-[0.08em] text-slate-400">经验 / 学历</div>
                      <div className="mt-2 font-medium text-slate-950">
                        {detailCandidate.years_experience || "-"} 年 / {detailCandidate.education_level || "-"}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="text-xs uppercase tracking-[0.08em] text-slate-400">城市 / 薪资</div>
                      <div className="mt-2 font-medium text-slate-950">
                        {detailCandidate.location || "-"} / {detailCandidate.expected_salary || "-"}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="text-xs uppercase tracking-[0.08em] text-slate-400">任务 / 岗位</div>
                      <div className="mt-2 font-medium text-slate-950">
                        {detailTask.id || "-"} / {detailJob.name || detailTask.job_id || "-"}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="text-xs uppercase tracking-[0.08em] text-slate-400">系统决策</div>
                      <div className="mt-2 flex items-center gap-2">
                        <Badge
                          variant={
                            detailScore.decision === "recommend"
                              ? "success"
                              : detailScore.decision === "reject"
                                ? "danger"
                                : "warn"
                          }
                        >
                          {formatDecision(detailScore.decision)}
                        </Badge>
                        <span className="text-sm font-medium text-slate-950">
                          {formatScore(detailScore.total_score)} 分
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button variant="secondary" asChild>
                      <a href={`/api/candidates/${detailCandidate.id}`} target="_blank" rel="noreferrer">
                        详情 JSON
                      </a>
                    </Button>
                    {detailSnapshot.resume_full_screenshot_path || detailSnapshot.screenshot_path ? (
                      <Button variant="secondary" asChild>
                        <a href={`/api/candidates/${detailCandidate.id}/screenshot`} target="_blank" rel="noreferrer">
                          完整简历截图
                        </a>
                      </Button>
                    ) : null}
                    {detailSnapshot.resume_markdown_path ? (
                      <Button variant="secondary" asChild>
                        <a href={`/api/candidates/${detailCandidate.id}/resume-markdown`} target="_blank" rel="noreferrer">
                          Markdown 简历
                        </a>
                      </Button>
                    ) : null}
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                <div className="space-y-6">
                  <Card>
                    <CardHeader>
                      <CardTitle>系统判断与证据</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex flex-wrap gap-2">
                        {(detailReasons.length ? detailReasons : ["暂无系统理由"]).map((entry) => (
                          <Badge key={entry} variant={detailScore.hard_filter_pass ? "success" : "warn"}>
                            {entry}
                          </Badge>
                        ))}
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                        {detailSnapshot.extracted_text || detailCandidate.raw_summary || "暂无结构化摘要。"}
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>标签</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex flex-wrap gap-2">
                        {detailTags.length ? detailTags.map((tag) => (
                          <Badge key={tag.id || tag.tag} variant="neutral">
                            {tag.tag}
                          </Badge>
                        )) : <Badge variant="neutral">暂无标签</Badge>}
                      </div>
                      <div className="flex gap-3">
                        <Input
                          value={tagInput}
                          placeholder="例如：在线教育测试 / 北京自动化测试"
                          onChange={(event) => setTagInput(event.target.value)}
                        />
                        <Button variant="secondary" onClick={addTag}>
                          <Plus className="size-4" />
                          添加
                        </Button>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>时间线</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ScrollArea className="h-[360px] pr-2">
                        <div className="space-y-4">
                          {detailTimeline.length ? detailTimeline.map((entry) => (
                            <div key={entry.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                              <div className="text-sm font-semibold text-slate-950">{timelineEventTitle(entry)}</div>
                              <div className="mt-1 text-xs text-slate-400">
                                {entry.operator || "system"} · {formatTime(entry.created_at)}
                              </div>
                              <div className="mt-3 text-sm leading-6 text-slate-600">
                                {timelineEventSummary(entry)}
                              </div>
                            </div>
                          )) : (
                            <EmptyState title="暂无时间线" description="该候选人还没有沉淀更多操作记录。" />
                          )}
                        </div>
                      </ScrollArea>
                    </CardContent>
                  </Card>
                </div>

                <div className="space-y-6">
                  <Card>
                    <CardHeader>
                      <CardTitle>自动打招呼</CardTitle>
                      <CardDescription>把这位候选人本次执行时使用的阈值、分数和动作结果放在一起，方便回头复盘。</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          variant={
                            latestGreetStatus === "success"
                              ? "success"
                              : latestGreetStatus === "failed"
                                ? "danger"
                                : "warn"
                          }
                        >
                          {candidateActionStatusLabels[latestGreetStatus] || latestGreetStatus || "未执行"}
                        </Badge>
                        {latestGreetAction?.created_at ? (
                          <span className="text-sm text-slate-500">{formatTime(latestGreetAction.created_at)}</span>
                        ) : null}
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                        <div>执行阈值：{formatThresholdLabel(latestGreetThreshold)}</div>
                        <div>候选人得分：{formatScore(latestGreetScore)}</div>
                        <div>动作说明：{latestGreetReason || "未记录额外说明"}</div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>快捷动作</CardTitle>
                    </CardHeader>
                    <CardContent className="grid gap-2">
                      <Button variant="secondary" onClick={() => void saveStage(quickActions.toContact)}>建议沟通</Button>
                      <Button variant="secondary" onClick={() => void saveStage(quickActions.needInfo)}>待补信息</Button>
                      <Button variant="secondary" onClick={() => void saveStage(quickActions.keepPool)}>加入人才库</Button>
                      <Button variant="secondary" onClick={() => void saveStage(quickActions.invited)}>标记已邀约</Button>
                      <Button variant="secondary" onClick={() => void saveStage(quickActions.reject)}>暂不沟通</Button>
                      <Button variant="destructive" onClick={() => void saveStage(quickActions.block)}>不再联系</Button>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>处理表单</CardTitle>
                      <CardDescription>
                        最近复核：{reviewSummary(detailReviews.at(-1))}。历史动作：
                        {detailActions.length
                          ? ` ${detailActions.slice(-3).reverse().map(actionSummary).filter(Boolean).join("；")}`
                          : " 暂无"}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label>Owner</Label>
                        <Input value={detailForm.owner} placeholder="hr_1" onChange={(event) => setDetailForm((current) => ({ ...current, owner: event.target.value }))} />
                      </div>
                      <div className="space-y-2">
                        <Label>当前阶段</Label>
                        <NativeSelect value={detailForm.current_stage} onChange={(event) => setDetailForm((current) => ({ ...current, current_stage: event.target.value }))}>
                          {stageOptions.map((entry) => (
                            <option key={entry} value={entry}>
                              {formatStage(entry)}
                            </option>
                          ))}
                        </NativeSelect>
                      </div>
                      <div className="space-y-2">
                        <Label>原因码</Label>
                        <NativeSelect value={detailForm.reason_code} onChange={(event) => setDetailForm((current) => ({ ...current, reason_code: event.target.value }))}>
                          <option value="">请选择</option>
                          {reasonCodeOptions.map((entry) => (
                            <option key={entry} value={entry}>
                              {reasonCodeLabels[entry] || entry}
                            </option>
                          ))}
                        </NativeSelect>
                      </div>
                      <div className="space-y-2">
                        <Label>最终决策</Label>
                        <NativeSelect value={detailForm.final_decision} onChange={(event) => setDetailForm((current) => ({ ...current, final_decision: event.target.value }))}>
                          <option value="">请选择</option>
                          {finalDecisionOptions.map((entry) => (
                            <option key={entry} value={entry}>
                              {finalDecisionLabels[entry] || entry}
                            </option>
                          ))}
                        </NativeSelect>
                      </div>
                      <div className="space-y-2">
                        <Label>最近沟通时间</Label>
                        <Input type="datetime-local" value={detailForm.last_contacted_at} onChange={(event) => setDetailForm((current) => ({ ...current, last_contacted_at: event.target.value }))} />
                      </div>
                      <div className="space-y-2">
                        <Label>最近沟通结果</Label>
                        <Input value={detailForm.last_contact_result} placeholder="已回复 / 待确认 / 无回复" onChange={(event) => setDetailForm((current) => ({ ...current, last_contact_result: event.target.value }))} />
                      </div>
                      <div className="space-y-2">
                        <Label>下次跟进时间</Label>
                        <Input type="datetime-local" value={detailForm.next_follow_up_at} onChange={(event) => setDetailForm((current) => ({ ...current, next_follow_up_at: event.target.value }))} />
                      </div>
                      <div className="space-y-2">
                        <Label>人才池状态</Label>
                        <Input value={detailForm.talent_pool_status} placeholder="核心储备 / 可二次激活" onChange={(event) => setDetailForm((current) => ({ ...current, talent_pool_status: event.target.value }))} />
                      </div>
                      <div className="space-y-2">
                        <Label>补充备注</Label>
                        <Textarea value={detailForm.reason_notes} placeholder="记录 HR 的判断、沟通情况或补充信息。" onChange={(event) => setDetailForm((current) => ({ ...current, reason_notes: event.target.value }))} />
                      </div>
                      <div className="flex flex-wrap gap-4 text-sm text-slate-600">
                        <label className="inline-flex items-center gap-2">
                          <input type="checkbox" checked={detailForm.reusable_flag} onChange={(event) => setDetailForm((current) => ({ ...current, reusable_flag: event.target.checked }))} />
                          标记为可复用
                        </label>
                        <label className="inline-flex items-center gap-2">
                          <input type="checkbox" checked={detailForm.do_not_contact} onChange={(event) => setDetailForm((current) => ({ ...current, do_not_contact: event.target.checked }))} />
                          标记为不再联系
                        </label>
                      </div>
                      <div className="grid gap-3">
                        <Button onClick={() => void saveStage()} disabled={saving || isPending}>
                          <Save className="size-4" />
                          {saving ? "保存中..." : "保存处理结果"}
                        </Button>
                        <Button variant="secondary" onClick={saveFollowUp} disabled={saving || isPending}>
                          仅保存跟进计划
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
