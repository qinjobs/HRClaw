import { useEffect, useMemo, useState } from "react";
import { RefreshCcw, Save, Sparkles } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { StatusBanner } from "@/components/shared/status-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { getJson, postJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import type { Phase2ScorecardRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ScorecardFormState {
  name: string;
  role_title: string;
  jd_text: string;
  summary: string;
  filter_location: string;
  filter_years_min: string;
  filter_age_min: string;
  filter_age_max: string;
  filter_education_min: string;
  must_have: string;
  nice_to_have: string;
  exclude: string;
  titles: string;
  industry: string;
  weight_must_have: string;
  weight_nice_to_have: string;
  weight_title_match: string;
  weight_industry_match: string;
  weight_experience: string;
  weight_education: string;
  weight_location: string;
  threshold_recommend: string;
  threshold_review: string;
  hard_filter_ratio: string;
  enforce_years: boolean;
  enforce_age: boolean;
  enforce_education: boolean;
  enforce_location: boolean;
  strict_exclude: boolean;
}

const defaultScorecardForm: ScorecardFormState = {
  name: "",
  role_title: "",
  jd_text: "",
  summary: "",
  filter_location: "",
  filter_years_min: "",
  filter_age_min: "",
  filter_age_max: "",
  filter_education_min: "",
  must_have: "",
  nice_to_have: "",
  exclude: "",
  titles: "",
  industry: "",
  weight_must_have: "42",
  weight_nice_to_have: "12",
  weight_title_match: "12",
  weight_industry_match: "8",
  weight_experience: "14",
  weight_education: "7",
  weight_location: "5",
  threshold_recommend: "75",
  threshold_review: "55",
  hard_filter_ratio: "0.5",
  enforce_years: false,
  enforce_age: false,
  enforce_education: false,
  enforce_location: false,
  strict_exclude: false,
};

const BUILTIN_ENGINE_TYPE = "builtin_formula";
const CUSTOM_ENGINE_TYPE = "generic_resume_match";
const BUILTIN_SCORING_KIND = "builtin_phase1";
const CUSTOM_SCORING_KIND = "custom_phase2";
const emptyBuiltinEditor = JSON.stringify(
  { name: "", hard_filters: [], thresholds: {}, weights: {}, schema_version: "phase1_builtin_v1" },
  null,
  2,
);

function splitLines(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function linesFromArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item || "")).join("\n") : "";
}

function toNumber(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function scorecardKindLabel(record?: Phase2ScorecardRecord | null) {
  return record?.scorecard_kind === BUILTIN_SCORING_KIND || record?.kind === BUILTIN_SCORING_KIND
    ? "内置 JD评分卡"
    : "自定义 JD评分卡";
}

function engineLabel(record?: Phase2ScorecardRecord | null) {
  return record?.engine_type === BUILTIN_ENGINE_TYPE ? "公式评分引擎" : "通用 JD 匹配引擎";
}

function statusToneFromMessage(message: string): "default" | "error" | "success" {
  if (message.includes("失败")) return "error";
  if (message.includes("完成") || message.includes("保存") || message.includes("生成")) return "success";
  return "default";
}

function ManagementMeta({
  label,
  value,
  subdued,
}: {
  label: string;
  value: string | number;
  subdued?: boolean;
}) {
  return (
    <div className={cn("rounded-[22px] border border-black/[0.06] bg-white/68 px-4 py-3", subdued && "bg-black/[0.02]")}>
      <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">{label}</div>
      <div className="mt-2 text-sm font-semibold tracking-[-0.02em] text-slate-950">{value}</div>
    </div>
  );
}

function FormSection({
  eyebrow,
  title,
  description,
  children,
  className,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("surface-muted p-5 md:p-6", className)}>
      <div className="mb-5">
        <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">{eyebrow}</div>
        <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h3>
        <p className="mt-2 text-sm leading-7 text-slate-500">{description}</p>
      </div>
      {children}
    </section>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onCheckedChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-[22px] border border-black/[0.05] bg-white/66 px-4 py-4">
      <div className="min-w-0">
        <div className="text-sm font-medium tracking-[-0.01em] text-slate-900">{label}</div>
        <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

export function Phase2Page() {
  const bootstrap = getBootstrap();
  const { pushToast } = useToast();
  const [scorecards, setScorecards] = useState<Phase2ScorecardRecord[]>([]);
  const [currentScorecardId, setCurrentScorecardId] = useState("");
  const [builderStatus, setBuilderStatus] = useState("等待操作...");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState<ScorecardFormState>(defaultScorecardForm);
  const [rawEditorText, setRawEditorText] = useState(emptyBuiltinEditor);

  const selectedScorecard = useMemo(
    () => scorecards.find((item) => item.id === currentScorecardId) || null,
    [currentScorecardId, scorecards],
  );
  const currentEngineType = selectedScorecard?.engine_type || CUSTOM_ENGINE_TYPE;
  const currentScorecardKind = selectedScorecard?.scorecard_kind || selectedScorecard?.kind || CUSTOM_SCORING_KIND;
  const isBuiltinFormula = currentEngineType === BUILTIN_ENGINE_TYPE;

  // Preview stays derived from the existing form state so visual refactors don't change save behavior.
  const preview = useMemo(
    () => ({
      schema_version: "phase2_scorecard_v1",
      name: form.name,
      role_title: form.role_title,
      jd_text: form.jd_text,
      summary: form.summary,
      filters: {
        location: form.filter_location || null,
        years_min: form.filter_years_min ? Number(form.filter_years_min) : null,
        age_min: form.filter_age_min ? Number(form.filter_age_min) : null,
        age_max: form.filter_age_max ? Number(form.filter_age_max) : null,
        education_min: form.filter_education_min || null,
      },
      must_have: splitLines(form.must_have),
      nice_to_have: splitLines(form.nice_to_have),
      exclude: splitLines(form.exclude),
      titles: splitLines(form.titles),
      industry: splitLines(form.industry),
      weights: {
        must_have: toNumber(form.weight_must_have, 42),
        nice_to_have: toNumber(form.weight_nice_to_have, 12),
        title_match: toNumber(form.weight_title_match, 12),
        industry_match: toNumber(form.weight_industry_match, 8),
        experience: toNumber(form.weight_experience, 14),
        education: toNumber(form.weight_education, 7),
        location: toNumber(form.weight_location, 5),
      },
      thresholds: {
        recommend_min: toNumber(form.threshold_recommend, 75),
        review_min: toNumber(form.threshold_review, 55),
      },
      hard_filters: {
        must_have_ratio_min: toNumber(form.hard_filter_ratio, 0.5),
        enforce_years: form.enforce_years,
        enforce_age: form.enforce_age,
        enforce_education: form.enforce_education,
        enforce_location: form.enforce_location,
        strict_exclude: form.strict_exclude,
      },
    }),
    [form],
  );

  const fillForm = (record?: Phase2ScorecardRecord | { scorecard?: Record<string, any>; id?: string; name?: string }) => {
    const scorecard = (record && "scorecard" in record ? record.scorecard : {}) || {};
    const nextId = (record && "id" in record && record.id) || "";
    setCurrentScorecardId(nextId);
    setRawEditorText(JSON.stringify(scorecard, null, 2));
    setForm({
      name: String(scorecard.name || ("name" in (record || {}) ? record?.name : "") || ""),
      role_title: String(scorecard.role_title || ""),
      jd_text: String(scorecard.jd_text || ("jd_text" in (record || {}) ? (record as any).jd_text : "") || ""),
      summary: String(scorecard.summary || ""),
      filter_location: String(scorecard.filters?.location || ""),
      filter_years_min:
        scorecard.filters?.years_min !== undefined && scorecard.filters?.years_min !== null
          ? String(scorecard.filters.years_min)
          : "",
      filter_age_min:
        scorecard.filters?.age_min !== undefined && scorecard.filters?.age_min !== null
          ? String(scorecard.filters.age_min)
          : "",
      filter_age_max:
        scorecard.filters?.age_max !== undefined && scorecard.filters?.age_max !== null
          ? String(scorecard.filters.age_max)
          : "",
      filter_education_min: String(scorecard.filters?.education_min || ""),
      must_have: linesFromArray(scorecard.must_have),
      nice_to_have: linesFromArray(scorecard.nice_to_have),
      exclude: linesFromArray(scorecard.exclude),
      titles: linesFromArray(scorecard.titles),
      industry: linesFromArray(scorecard.industry),
      weight_must_have: String(scorecard.weights?.must_have ?? 42),
      weight_nice_to_have: String(scorecard.weights?.nice_to_have ?? 12),
      weight_title_match: String(scorecard.weights?.title_match ?? 12),
      weight_industry_match: String(scorecard.weights?.industry_match ?? 8),
      weight_experience: String(scorecard.weights?.experience ?? 14),
      weight_education: String(scorecard.weights?.education ?? 7),
      weight_location: String(scorecard.weights?.location ?? 5),
      threshold_recommend: String(scorecard.thresholds?.recommend_min ?? 75),
      threshold_review: String(scorecard.thresholds?.review_min ?? 55),
      hard_filter_ratio: String(scorecard.hard_filters?.must_have_ratio_min ?? 0.5),
      enforce_years: Boolean(scorecard.hard_filters?.enforce_years),
      enforce_age: Boolean(scorecard.hard_filters?.enforce_age),
      enforce_education: Boolean(scorecard.hard_filters?.enforce_education),
      enforce_location: Boolean(scorecard.hard_filters?.enforce_location),
      strict_exclude: Boolean(scorecard.hard_filters?.strict_exclude),
    });
  };

  const loadScorecards = async (preferredId?: string) => {
    const data = await getJson<{ items: Phase2ScorecardRecord[] }>("/api/v2/scorecards");
    setScorecards(data.items || []);
    const activeId = preferredId || currentScorecardId || data.items?.[0]?.id || "";
    if (activeId) {
      const record = (data.items || []).find((item) => item.id === activeId);
      if (record) fillForm(record);
      setCurrentScorecardId(activeId);
    }
  };

  useEffect(() => {
    void loadScorecards();
  }, []);

  const generateScorecard = async () => {
    if (isBuiltinFormula) {
      pushToast({ tone: "error", title: "第一阶段公式卡不支持 JD 自动生成" });
      return;
    }
    if (!form.jd_text.trim()) {
      pushToast({ tone: "error", title: "请先贴入 JD 原文" });
      return;
    }
    setIsGenerating(true);
    try {
      const payload = await postJson<{ scorecard: Record<string, any> }>("/api/v2/scorecards/generate", {
        jd_text: form.jd_text.trim(),
        name: form.name.trim() || form.role_title.trim() || undefined,
      });
      fillForm({ scorecard: payload.scorecard });
      setBuilderStatus("已根据 JD 生成初始评分卡，请确认后保存。");
      pushToast({ tone: "success", title: "评分卡已生成" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "生成失败";
      setBuilderStatus(`生成失败：${message}`);
      pushToast({ tone: "error", title: "生成失败", description: message });
    } finally {
      setIsGenerating(false);
    }
  };

  const saveScorecard = async () => {
    setIsSaving(true);
    try {
      const scorecardPayload = isBuiltinFormula ? JSON.parse(rawEditorText) : preview;
      const data = await postJson<{ item: Phase2ScorecardRecord }>("/api/v2/scorecards", {
        id: currentScorecardId || undefined,
        name: isBuiltinFormula
          ? String(scorecardPayload.name || selectedScorecard?.name || "").trim()
          : form.name.trim() || preview.name,
        scorecard: scorecardPayload,
        scorecard_kind: currentScorecardKind,
        engine_type: currentEngineType,
        schema_version: String(
          (isBuiltinFormula ? scorecardPayload.schema_version : preview.schema_version) ||
            selectedScorecard?.schema_version ||
            "",
        ),
        supports_resume_import: isBuiltinFormula ? false : true,
        editable: selectedScorecard?.editable ?? true,
        system_managed: selectedScorecard?.system_managed ?? false,
        created_by: "hr_ui",
      });
      await loadScorecards(data.item.id);
      setBuilderStatus(`评分卡已保存：${data.item.name}`);
      pushToast({ tone: "success", title: "评分卡已保存", description: data.item.name });
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setBuilderStatus(`保存失败：${message}`);
      pushToast({ tone: "error", title: "保存失败", description: message });
    } finally {
      setIsSaving(false);
    }
  };

  const previewText = isBuiltinFormula ? rawEditorText : JSON.stringify(preview, null, 2);

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="JD评分卡"
      titleClassName="text-3xl font-semibold tracking-[-0.05em] md:text-[2.5rem]"
      showPageTitle={false}
      showWorkspacePanel={false}
    >
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-black/[0.06] bg-white/54">
          <div className="max-w-3xl">
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
              Unified JD Scorecards
            </div>
            <CardTitle className="mt-2">JD评分卡工作台</CardTitle>
            <CardDescription>
              将评分卡选择、编辑、预览和状态反馈收拢到同一个主工作区里，减少操作来回跳转。
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-6 pt-6">
          <div className="grid gap-3 2xl:grid-cols-[minmax(0,1fr)_auto_auto]">
            <NativeSelect
              value={currentScorecardId}
              onChange={(event) => {
                const record = scorecards.find((item) => item.id === event.target.value);
                setCurrentScorecardId(event.target.value);
                if (record) fillForm(record);
              }}
            >
              <option value="">选择已有评分卡</option>
              {scorecards.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {scorecardKindLabel(item)}
                </option>
              ))}
            </NativeSelect>
            <Button
              variant="secondary"
              onClick={() => {
                setCurrentScorecardId("");
                setForm(defaultScorecardForm);
                setRawEditorText(emptyBuiltinEditor);
                setBuilderStatus("已切换为新建模式。先贴 JD，再生成评分卡。");
              }}
            >
              新建评分卡
            </Button>
            <Button variant="secondary" onClick={() => void loadScorecards(currentScorecardId)}>
              <RefreshCcw className="size-4" />
              刷新列表
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            <Badge variant={isBuiltinFormula ? "info" : "success"}>{scorecardKindLabel(selectedScorecard)}</Badge>
            <Badge variant="neutral">{engineLabel(selectedScorecard)}</Badge>
            <Badge variant={selectedScorecard?.supports_resume_import ? "success" : "neutral"}>
              {selectedScorecard?.supports_resume_import ? "支持批量导入" : "仅插件 / 任务评分"}
            </Badge>
            {selectedScorecard?.system_managed ? <Badge variant="neutral">系统预置</Badge> : null}
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.24fr)_360px] 2xl:grid-cols-[minmax(0,1.32fr)_400px]">
            <div className="space-y-5">
              {isBuiltinFormula ? (
                <FormSection
                  eyebrow="Formula Editor"
                  title="第一阶段公式评分卡"
                  description="内置公式卡已统一进入 JD评分卡，但执行时依然走原来的第一阶段评分引擎。这里保留 JSON 级编辑能力，避免破坏既有打分结果。"
                >
                  <StatusBanner
                    title="编辑建议"
                    description="优先调整 name、hard_filters、thresholds 与 weights。若需变更评分结构，请确认插件和任务链路的兼容性。"
                  />
                  <div className="mt-5 space-y-2">
                    <Label>公式卡 JSON</Label>
                    <Textarea
                      className="min-h-[480px] font-mono text-xs leading-7"
                      value={rawEditorText}
                      onChange={(event) => setRawEditorText(event.target.value)}
                    />
                  </div>
                </FormSection>
              ) : (
                <Tabs key={currentScorecardId || "new-scorecard"} defaultValue="basics">
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="basics">基础信息</TabsTrigger>
                    <TabsTrigger value="rules">规则与权重</TabsTrigger>
                    <TabsTrigger value="thresholds">阈值与硬筛</TabsTrigger>
                  </TabsList>

                  <TabsContent value="basics">
                    <FormSection
                      eyebrow="Basics"
                      title="职位定义"
                      description="用更清晰的排版承接 JD 原文、岗位标题和摘要，先确保岗位表达准确，再进入规则与阈值层。"
                    >
                      <div className="grid gap-5 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label>评分卡名称</Label>
                          <Input
                            value={form.name}
                            placeholder="例如：前端开发-外研社"
                            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>岗位标题</Label>
                          <Input
                            value={form.role_title}
                            placeholder="例如：高级前端开发工程师"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, role_title: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>JD 原文</Label>
                          <Textarea
                            className="min-h-[260px]"
                            value={form.jd_text}
                            placeholder="粘贴完整 JD，生成器会根据内容提取必须项、加分项和阈值建议。"
                            onChange={(event) => setForm((current) => ({ ...current, jd_text: event.target.value }))}
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>摘要</Label>
                          <Textarea
                            value={form.summary}
                            placeholder="用一句话概括岗位核心要求，便于后续快速浏览。"
                            onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))}
                          />
                        </div>
                      </div>
                    </FormSection>
                  </TabsContent>

                  <TabsContent value="rules">
                    <FormSection
                      eyebrow="Rules"
                      title="筛选规则与权重"
                      description="把筛选条件与匹配权重拆分成更安静的表单组，方便 HR 快速调整而不会被视觉噪音打断。"
                    >
                      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
                        <div className="space-y-2">
                          <Label>城市</Label>
                          <Input
                            value={form.filter_location}
                            placeholder="例如：北京 / 上海"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, filter_location: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>最低年限</Label>
                          <Input
                            value={form.filter_years_min}
                            placeholder="例如：3"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, filter_years_min: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>最低年龄</Label>
                          <Input
                            value={form.filter_age_min}
                            placeholder="例如：22"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, filter_age_min: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>最高年龄</Label>
                          <Input
                            value={form.filter_age_max}
                            placeholder="例如：35"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, filter_age_max: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>最低学历</Label>
                          <Input
                            value={form.filter_education_min}
                            placeholder="例如：本科"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, filter_education_min: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>必备项</Label>
                          <Textarea
                            value={form.must_have}
                            placeholder="每行一项，例如：React / TypeScript / 工程化"
                            onChange={(event) => setForm((current) => ({ ...current, must_have: event.target.value }))}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>加分项</Label>
                          <Textarea
                            value={form.nice_to_have}
                            placeholder="每行一项，例如：低代码平台 / 国际化经验"
                            onChange={(event) =>
                              setForm((current) => ({ ...current, nice_to_have: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>排除项</Label>
                          <Textarea
                            value={form.exclude}
                            placeholder="每行一项，例如：仅实习 / 完全转岗"
                            onChange={(event) => setForm((current) => ({ ...current, exclude: event.target.value }))}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>岗位标题关键词</Label>
                          <Textarea
                            value={form.titles}
                            placeholder="每行一项，例如：前端工程师 / Web 开发"
                            onChange={(event) => setForm((current) => ({ ...current, titles: event.target.value }))}
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>行业关键词</Label>
                          <Textarea
                            value={form.industry}
                            placeholder="每行一项，例如：教育科技 / 内容平台"
                            onChange={(event) => setForm((current) => ({ ...current, industry: event.target.value }))}
                          />
                        </div>
                      </div>

                      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        {[
                          ["必备项权重", "weight_must_have"],
                          ["加分项权重", "weight_nice_to_have"],
                          ["Title 匹配", "weight_title_match"],
                          ["行业匹配", "weight_industry_match"],
                          ["经验匹配", "weight_experience"],
                          ["学历匹配", "weight_education"],
                          ["城市匹配", "weight_location"],
                        ].map(([label, key]) => (
                          <div key={key} className="space-y-2">
                            <Label>{label}</Label>
                            <Input
                              value={form[key as keyof ScorecardFormState] as string}
                              onChange={(event) =>
                                setForm((current) => ({ ...current, [key]: event.target.value }))
                              }
                            />
                          </div>
                        ))}
                      </div>
                    </FormSection>
                  </TabsContent>

                  <TabsContent value="thresholds">
                    <FormSection
                      eyebrow="Thresholds"
                      title="阈值与硬筛开关"
                      description="把最终决策阈值和硬性规则独立成一层，让 HR 能更清楚地控制推荐、复核与淘汰边界。"
                    >
                      <div className="grid gap-5 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label>Recommend 阈值</Label>
                          <Input
                            value={form.threshold_recommend}
                            onChange={(event) =>
                              setForm((current) => ({ ...current, threshold_recommend: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Review 阈值</Label>
                          <Input
                            value={form.threshold_review}
                            onChange={(event) =>
                              setForm((current) => ({ ...current, threshold_review: event.target.value }))
                            }
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>必备项命中比例</Label>
                          <Input
                            value={form.hard_filter_ratio}
                            onChange={(event) =>
                              setForm((current) => ({ ...current, hard_filter_ratio: event.target.value }))
                            }
                          />
                        </div>
                      </div>

                      <div className="mt-6 grid gap-3">
                        <ToggleRow
                          label="强制校验年限"
                          description="候选人年限不足时，直接触发硬筛而不是仅降低得分。"
                          checked={form.enforce_years}
                          onCheckedChange={(checked) =>
                            setForm((current) => ({ ...current, enforce_years: checked }))
                          }
                        />
                        <ToggleRow
                          label="强制校验年龄范围"
                          description="年龄不在 JD 定义范围内时，直接触发硬筛。"
                          checked={form.enforce_age}
                          onCheckedChange={(checked) =>
                            setForm((current) => ({ ...current, enforce_age: checked }))
                          }
                        />
                        <ToggleRow
                          label="强制校验学历"
                          description="当岗位学历要求为硬条件时启用，更适合校招或标准化岗位。"
                          checked={form.enforce_education}
                          onCheckedChange={(checked) =>
                            setForm((current) => ({ ...current, enforce_education: checked }))
                          }
                        />
                        <ToggleRow
                          label="强制校验城市"
                          description="对必须驻场或有明确办公地要求的岗位更有帮助。"
                          checked={form.enforce_location}
                          onCheckedChange={(checked) =>
                            setForm((current) => ({ ...current, enforce_location: checked }))
                          }
                        />
                        <ToggleRow
                          label="严格排除 exclude 关键词"
                          description="命中排除词后直接降为淘汰，更适合对风险项较敏感的岗位。"
                          checked={form.strict_exclude}
                          onCheckedChange={(checked) =>
                            setForm((current) => ({ ...current, strict_exclude: checked }))
                          }
                        />
                      </div>
                    </FormSection>
                  </TabsContent>
                </Tabs>
              )}

              <div className="flex flex-wrap gap-3 pt-1">
                {!isBuiltinFormula ? (
                  <Button variant="secondary" onClick={generateScorecard} disabled={isGenerating}>
                    <Sparkles className="size-4" />
                    {isGenerating ? "生成中..." : "根据 JD 生成评分卡"}
                  </Button>
                ) : null}
                <Button onClick={saveScorecard} disabled={isSaving}>
                  <Save className="size-4" />
                  {isSaving ? "保存中..." : "保存评分卡"}
                </Button>
              </div>
            </div>

            <aside className="space-y-3 xl:sticky xl:top-28 xl:self-start">
              <div className="surface-muted p-4">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">Current Card</div>
                <div className="mt-2 text-lg font-semibold tracking-[-0.03em] text-slate-950">
                  {selectedScorecard?.name || form.name || "新建评分卡"}
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  当前编辑面板会根据评分卡引擎自动切换为公式卡编辑器或 JD 表单模式。
                </p>
                <div className="mt-4 grid gap-2.5">
                  <ManagementMeta label="评分卡类型" value={scorecardKindLabel(selectedScorecard)} />
                  <ManagementMeta label="引擎类型" value={engineLabel(selectedScorecard)} />
                  <ManagementMeta
                    label="导入能力"
                    value={selectedScorecard?.supports_resume_import ? "支持批量导入" : "仅插件 / 任务评分"}
                  />
                  <ManagementMeta label="更新时间" value={selectedScorecard?.updated_at || "尚未保存"} subdued />
                </div>
              </div>

              <StatusBanner
                tone={statusToneFromMessage(builderStatus)}
                title="构建状态"
                description={builderStatus}
              />

              <div className="surface-strong overflow-hidden">
                <div className="border-b border-white/10 px-5 py-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
                    Live Preview
                  </div>
                  <div className="mt-2 text-lg font-semibold tracking-[-0.03em] text-white">
                    评分卡 JSON 预览
                  </div>
                </div>
                <ScrollArea className="h-[480px]">
                  <pre className="px-5 py-4 text-xs leading-7 text-slate-300">{previewText}</pre>
                </ScrollArea>
              </div>
            </aside>
          </div>
        </CardContent>
      </Card>

    </AppShell>
  );
}
