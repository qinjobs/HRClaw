import { startTransition, useState } from "react";
import { RefreshCcw, Search as SearchIcon } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { EmptyState } from "@/components/shared/empty-state";
import { ListEditor } from "@/components/shared/list-editor";
import { PageSection } from "@/components/shared/page-section";
import { StatTile } from "@/components/shared/stat-tile";
import { StatusBanner } from "@/components/shared/status-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { getJson, postJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import { compactText, formatScore } from "@/lib/format";
import type { SearchResultItem, SearchRunPayload } from "@/lib/types";
import { useToast } from "@/components/ui/toast";

function safeLink(entry: Record<string, string> | undefined, key: string) {
  return entry && typeof entry[key] === "string" ? entry[key] : "";
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function SearchPage() {
  const bootstrap = getBootstrap();
  const { pushToast } = useToast();
  const [jobTitle, setJobTitle] = useState("");
  const [mustHave, setMustHave] = useState(["", ""]);
  const [bonus, setBonus] = useState(["", "", ""]);
  const [location, setLocation] = useState("");
  const [yearsMin, setYearsMin] = useState("");
  const [educationMin, setEducationMin] = useState("");
  const [topK, setTopK] = useState("20");
  const [queryNotes, setQueryNotes] = useState("");
  const [explain, setExplain] = useState(true);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [metaText, setMetaText] = useState("等待操作...");
  const [resultsStatus, setResultsStatus] = useState("等待开始匹配...");
  const [isIndexing, setIsIndexing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [searchRunId, setSearchRunId] = useState("");

  const collectConditions = (items: string[]) => items.map((item) => item.trim()).filter(Boolean);

  const composeQuery = () => {
    const mustValues = collectConditions(mustHave);
    const bonusValues = collectConditions(bonus);
    const parts = [];
    if (jobTitle.trim()) parts.push(jobTitle.trim());
    if (mustValues.length) parts.push(`必备：${mustValues.join("；")}`);
    if (bonusValues.length) parts.push(`加分：${bonusValues.join("；")}`);
    if (queryNotes.trim()) parts.push(queryNotes.trim());
    return { rawQuery: parts.join("\n"), mustValues };
  };

  const loadRun = async (runId: string) => {
    for (let index = 0; index < 20; index += 1) {
      const run = await getJson<any>(`/api/v3/search/runs/${encodeURIComponent(runId)}`);
      startTransition(() => {
        setResults(run.results || []);
        setMetaText(
          `Run: ${runId}\nStatus: ${run.status}\nDegraded: ${(run.degraded || []).join(", ") || "none"}\nQueryIntent: ${JSON.stringify(run.query_intent || {}, null, 2)}`,
        );
      });
      setResultsStatus(run.status === "completed" ? "匹配完成" : "正在补充解释与重排...");
      if (run.status === "completed") return;
      await delay(1200);
    }
  };

  const upsertIndex = async () => {
    setIsIndexing(true);
    setMetaText("正在把本地候选人回灌到搜索索引...");
    try {
      const data = await postJson<any>("/api/v3/search/index/upsert", {});
      setMetaText(
        `索引完成\nProfiles: ${data.upserted_profiles}\nChunks: ${data.upserted_chunks}\nDegraded: ${(data.degraded || []).join(", ") || "none"}\n耗时: ${data.duration_ms}ms`,
      );
      pushToast({ tone: "success", title: "索引已更新" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "索引失败";
      setMetaText(`索引失败：${message}`);
      pushToast({ tone: "error", title: "索引失败", description: message });
    } finally {
      setIsIndexing(false);
    }
  };

  const searchNow = async () => {
    const queryPayload = composeQuery();
    if (!queryPayload.rawQuery.trim()) {
      pushToast({ tone: "error", title: "请先填写职位概述或筛选条件" });
      return;
    }
    setIsSearching(true);
    setResultsStatus("正在匹配中...");
    setMetaText("开始搜索...");
    try {
      const filters: Record<string, unknown> = {};
      if (location.trim()) filters.location = location.trim();
      if (yearsMin.trim()) filters.years_min = Number(yearsMin);
      if (educationMin) filters.education_min = educationMin;
      if (queryPayload.mustValues.length) filters.skills = queryPayload.mustValues;

      const payload = await postJson<SearchRunPayload>("/api/v3/search/query", {
        query_text: queryPayload.rawQuery,
        filters,
        top_k: Number(topK || 20),
        explain,
      });
      setSearchRunId(payload.search_run_id);
      startTransition(() => {
        setResults(payload.results || []);
        setMetaText(`Run: ${payload.search_run_id}\nStatus: ${payload.status}\nQueryIntent: ${JSON.stringify(payload.query_intent || {}, null, 2)}`);
      });
      setResultsStatus(payload.status === "completed" ? "匹配完成" : "已返回首批结果，正在补充解释...");
      if (payload.status !== "completed" && payload.search_run_id) {
        await loadRun(payload.search_run_id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "搜索失败";
      setResults([]);
      setMetaText(`搜索失败：${message}`);
      setResultsStatus("匹配失败");
      pushToast({ tone: "error", title: "搜索失败", description: message });
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="高级搜索"
      subtitle="保留原有 query、回灌索引、解释与重排逻辑，但把筛选结构、结果密度和反馈节奏重构成产品级检索后台。"
    >
      <div className="grid gap-4 md:grid-cols-3">
        <StatTile label="匹配模式" value={explain ? "检索 + 解释" : "仅检索"} hint="解释开启时会继续补充风险点与建议追问" />
        <StatTile label="返回数量" value={topK} hint="接口仍走原有 top_k 字段" />
        <StatTile label="搜索 Run" value={searchRunId || "-"} hint="用于查看后续重排与解释状态" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <div className="space-y-6">
          <Card className="sticky top-24">
            <CardHeader>
              <CardTitle>搜索条件</CardTitle>
              <CardDescription>按原有字段拼接 query_text，同时保留结构化 filters 和 explain 开关。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="jobTitle">岗位概述 / 职位名称</Label>
                <Input
                  id="jobTitle"
                  placeholder="例如：Python开发工程师 / QA 测试工程师"
                  value={jobTitle}
                  onChange={(event) => setJobTitle(event.target.value)}
                />
              </div>

              <ListEditor
                label="必备条件"
                description="会同步进入 query_text，也会透传到 filters.skills。"
                values={mustHave}
                onChange={setMustHave}
                placeholder="例如：Python / Linux / Charles / 在线教育"
                minimumRows={2}
              />

              <ListEditor
                label="加分项"
                description="只影响 query_text 的补充语义，不改变现有接口结构。"
                values={bonus}
                onChange={setBonus}
                placeholder="例如：AI 项目 / 中大型系统 / 自动化测试"
                minimumRows={3}
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="location">城市</Label>
                  <Input id="location" placeholder="北京" value={location} onChange={(event) => setLocation(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="yearsMin">最低年限</Label>
                  <Input id="yearsMin" type="number" min="0" max="30" step="0.5" value={yearsMin} onChange={(event) => setYearsMin(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="educationMin">最低学历</Label>
                  <NativeSelect id="educationMin" value={educationMin} onChange={(event) => setEducationMin(event.target.value)}>
                    <option value="">不限</option>
                    <option value="大专">大专</option>
                    <option value="本科">本科</option>
                    <option value="硕士">硕士</option>
                    <option value="博士">博士</option>
                  </NativeSelect>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="topK">返回数量</Label>
                  <Input id="topK" type="number" min="1" max="20" value={topK} onChange={(event) => setTopK(event.target.value)} />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="queryNotes">补充说明 / JD 原文</Label>
                <Textarea
                  id="queryNotes"
                  placeholder="可选：补充业务背景、行业要求、排除条件或整段 JD 原文。"
                  value={queryNotes}
                  onChange={(event) => setQueryNotes(event.target.value)}
                  className="min-h-[140px]"
                />
              </div>

              <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div>
                  <div className="text-sm font-medium text-slate-900">生成 AI 推荐理由、风险点和建议追问</div>
                  <div className="text-sm text-slate-500">关闭后只返回检索结果，不等待解释层补充。</div>
                </div>
                <Switch checked={explain} onCheckedChange={setExplain} />
              </div>

              <div className="flex flex-wrap gap-3">
                <Button variant="secondary" onClick={upsertIndex} disabled={isIndexing}>
                  <RefreshCcw className="size-4" />
                  {isIndexing ? "回灌中..." : "回灌索引"}
                </Button>
                <Button onClick={searchNow} disabled={isSearching}>
                  <SearchIcon className="size-4" />
                  {isSearching ? "匹配中..." : "立即匹配"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <PageSection
            title="搜索状态"
            description="弱化噪音，把用户最关心的“现在发生了什么、是否可继续操作”放在页面最上层。"
            actions={<Badge variant="neutral">{resultsStatus}</Badge>}
          >
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <Card>
                <CardHeader>
                  <CardTitle>推荐简历</CardTitle>
                  <CardDescription>
                    结果保持原接口返回结构，卡片只重排了信息层级和操作入口。
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {!results.length ? (
                    <EmptyState
                      title="暂无结果"
                      description="先回灌索引，或调整左侧招聘要求后再开始匹配。"
                    />
                  ) : (
                    <div className="space-y-4">
                      {results.map((item) => {
                        const tone =
                          item.final_recommendation === "recommend"
                            ? "success"
                            : item.final_recommendation === "reject"
                              ? "danger"
                              : "warn";
                        return (
                          <Card key={`${item.resume_profile_id}-${item.rank}`} className="border-slate-200 shadow-none">
                            <CardContent className="p-5">
                              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <div className="text-lg font-semibold text-slate-950">
                                      {item.name || "未命名候选人"}
                                    </div>
                                    <Badge variant={tone}>
                                      {item.final_recommendation === "recommend"
                                        ? "建议沟通"
                                        : item.final_recommendation === "reject"
                                          ? "暂不沟通"
                                          : "继续复核"}
                                    </Badge>
                                    <Badge variant="neutral">
                                      {item.hard_filter_pass ? "条件通过" : "条件待确认"}
                                    </Badge>
                                  </div>
                                  <div className="mt-2 text-sm text-slate-500">
                                    {[item.years_experience ? `${item.years_experience} 年` : "", item.education_level || "", item.city || ""]
                                      .filter(Boolean)
                                      .join(" · ") || "信息待补充"}
                                  </div>
                                  <div className="mt-3 text-sm font-medium text-slate-900">
                                    {item.latest_company || "-"} · {item.latest_title || "-"}
                                  </div>
                                  <p className="mt-3 text-sm leading-6 text-slate-600">
                                    {compactText(item.matched_evidence?.join("；") || "命中本地简历库中的多维证据，建议继续查看详情确认。", 180)}
                                  </p>
                                  <div className="mt-4 flex flex-wrap gap-2">
                                    {(item.risk_flags || []).slice(0, 2).map((entry) => (
                                      <Badge key={`risk-${entry}`} variant="warn">
                                        风险 · {entry}
                                      </Badge>
                                    ))}
                                    {(item.interview_questions || []).slice(0, 2).map((entry) => (
                                      <Badge key={`ask-${entry}`} variant="info">
                                        追问 · {entry}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                                <div className="flex shrink-0 flex-col items-start gap-3 lg:items-end">
                                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-right">
                                    <div className="text-xs font-medium uppercase tracking-[0.08em] text-slate-400">
                                      综合分
                                    </div>
                                    <div className="text-2xl font-semibold text-slate-950">
                                      {formatScore(item.total_score)}
                                    </div>
                                  </div>
                                  <div className="flex flex-wrap justify-end gap-2">
                                    {safeLink(item.resume_entry, "detail_api_path") ? (
                                      <Button variant="secondary" asChild>
                                        <a href={safeLink(item.resume_entry, "detail_api_path")} target="_blank" rel="noreferrer">
                                          查看详情
                                        </a>
                                      </Button>
                                    ) : null}
                                    <Button variant="ghost" asChild>
                                      <a
                                        href={`/api/v3/candidates/${encodeURIComponent(item.resume_profile_id)}/search-profile`}
                                        target="_blank"
                                        rel="noreferrer"
                                      >
                                        Profile JSON
                                      </a>
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>运行元信息</CardTitle>
                  <CardDescription>保留原 metaBox，但改成更易读的运行面板和代码视图。</CardDescription>
                </CardHeader>
                <CardContent>
                  <StatusBanner
                    loading={isSearching}
                    title={resultsStatus}
                    description={searchRunId ? `当前 Run：${searchRunId}` : "还未开始搜索。"}
                  />
                  <ScrollArea className="mt-4 h-[420px] rounded-2xl border border-slate-200 bg-slate-950 p-4">
                    <pre className="text-xs leading-6 text-slate-300">{metaText}</pre>
                  </ScrollArea>
                </CardContent>
              </Card>
            </div>
          </PageSection>
        </div>
      </div>
    </AppShell>
  );
}
