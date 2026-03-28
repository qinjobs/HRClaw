import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, FileUp, RefreshCcw } from "lucide-react";
import { useLocation } from "react-router-dom";

import { AppShell } from "@/components/layout/app-shell";
import { EmptyState } from "@/components/shared/empty-state";
import { StatTile } from "@/components/shared/stat-tile";
import { StatusBanner } from "@/components/shared/status-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { getJson, postJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import { formatScore } from "@/lib/format";
import type { Phase2ScorecardRecord, ResumeImportBatch, ResumeImportResult } from "@/lib/types";
import { cn } from "@/lib/utils";

function statusToneFromMessage(message: string): "default" | "error" | "success" {
  if (message.includes("失败")) return "error";
  if (message.includes("完成") || message.includes("成功") || message.includes("已加载")) return "success";
  return "default";
}

function decisionVariant(decision?: string | null) {
  if (decision === "recommend") return "success";
  if (decision === "reject") return "danger";
  return "warn";
}

function decisionLabel(decision?: string | null) {
  if (decision === "recommend") return "建议沟通";
  if (decision === "reject") return "暂不沟通";
  if (decision === "review") return "继续复核";
  return decision || "-";
}

function ImportMeta({
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

export function ResumeImportsPage() {
  const bootstrap = getBootstrap();
  const location = useLocation();
  const { pushToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [scorecards, setScorecards] = useState<Phase2ScorecardRecord[]>([]);
  const [importScorecardId, setImportScorecardId] = useState("");
  const [batches, setBatches] = useState<ResumeImportBatch[]>([]);
  const [currentBatchId, setCurrentBatchId] = useState("");
  const [currentBatch, setCurrentBatch] = useState<ResumeImportBatch | null>(null);
  const [batchResults, setBatchResults] = useState<ResumeImportResult[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [batchName, setBatchName] = useState("");
  const [importStatus, setImportStatus] = useState("请选择评分卡并导入简历。");
  const [isImporting, setIsImporting] = useState(false);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);

  const preferredScorecardId = useMemo(
    () => new URLSearchParams(location.search).get("scorecardId") || "",
    [location.search],
  );
  const importableScorecards = useMemo(() => scorecards.filter((item) => item.supports_resume_import), [scorecards]);
  const selectedScorecard = useMemo(
    () => importableScorecards.find((item) => item.id === importScorecardId) || null,
    [importScorecardId, importableScorecards],
  );

  const loadScorecards = async (preferredId?: string) => {
    const data = await getJson<{ items: Phase2ScorecardRecord[] }>("/api/v2/scorecards");
    const items = (data.items || []).filter((item) => item.supports_resume_import);
    setScorecards(items);
    const nextId =
      (preferredId && items.some((item) => item.id === preferredId) ? preferredId : "") ||
      (importScorecardId && items.some((item) => item.id === importScorecardId) ? importScorecardId : "") ||
      items[0]?.id ||
      "";
    setImportScorecardId(nextId);
  };

  const loadBatchDetail = async (batchId: string) => {
    const data = await getJson<{ batch: ResumeImportBatch; results: ResumeImportResult[] }>(
      `/api/v2/resume-imports/${encodeURIComponent(batchId)}`,
    );
    setCurrentBatchId(batchId);
    setCurrentBatch(data.batch || null);
    setBatchResults(data.results || []);
    setImportStatus(`已加载批次：${data.batch?.batch_name || batchId}`);
  };

  const loadBatches = async (preferredId?: string) => {
    setIsLoadingBatches(true);
    try {
      const data = await getJson<{ items: ResumeImportBatch[] }>("/api/v2/resume-imports");
      setBatches(data.items || []);
      const activeId = preferredId || currentBatchId || data.items?.[0]?.id || "";
      if (activeId) {
        await loadBatchDetail(activeId);
      } else {
        setCurrentBatch(null);
        setBatchResults([]);
      }
    } finally {
      setIsLoadingBatches(false);
    }
  };

  useEffect(() => {
    void Promise.all([loadScorecards(preferredScorecardId), loadBatches()]);
  }, [preferredScorecardId]);

  const readFileAsBase64 = (file: File) =>
    new Promise<{ name: string; size: number; content_base64: string }>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
        resolve({ name: file.name, size: file.size, content_base64: base64 });
      };
      reader.onerror = () => reject(reader.error || new Error("文件读取失败"));
      reader.readAsDataURL(file);
    });

  const importFiles = async () => {
    if (!importScorecardId) {
      pushToast({ tone: "error", title: "请先选择评分卡" });
      return;
    }
    if (!selectedFiles.length) {
      pushToast({ tone: "error", title: "请先选择文件" });
      return;
    }
    setIsImporting(true);
    setImportStatus("正在读取文件并导入...");
    try {
      const files = await Promise.all(selectedFiles.map((file) => readFileAsBase64(file)));
      const data = await postJson<{ batch: ResumeImportBatch }>("/api/v2/resume-imports", {
        scorecard_id: importScorecardId,
        batch_name: batchName.trim(),
        created_by: "hr_ui",
        files,
      });
      setSelectedFiles([]);
      setBatchName("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadBatches(data.batch.id);
      setImportStatus(`导入完成：${data.batch.batch_name || data.batch.id}`);
      pushToast({ tone: "success", title: "批量导入完成" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "导入失败";
      setImportStatus(`导入失败：${message}`);
      pushToast({ tone: "error", title: "导入失败", description: message });
    } finally {
      setIsImporting(false);
    }
  };

  const summaryBatch: Partial<ResumeImportBatch> = currentBatch || {};

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="简历导入"
      subtitle="把批量导入、OCR 解析、自动评分和批次回看单独收敛成一页，方便 HR 在同一视图里完成筛选闭环。"
    >
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <StatTile label="可导入评分卡" value={importableScorecards.length} hint="仅展示支持简历导入的 JD 卡" />
        <StatTile label="导入批次" value={batches.length} hint="支持随时回看历史批次结果" />
        <StatTile
          label="已处理 / 总文件"
          value={`${summaryBatch.processed_files || 0} / ${summaryBatch.total_files || 0}`}
          hint="当前选中批次的处理进度"
        />
        <StatTile label="建议沟通" value={summaryBatch.recommend_count || 0} hint="当前批次 recommend 数量" />
        <StatTile
          label="复核 / 暂不沟通"
          value={`${summaryBatch.review_count || 0} / ${summaryBatch.reject_count || 0}`}
          hint="当前批次 review / reject"
        />
      </section>

      <section className="grid gap-8 xl:grid-cols-[minmax(0,1.06fr)_420px] 2xl:grid-cols-[minmax(0,1.14fr)_460px]">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-end 2xl:justify-between">
              <div className="max-w-3xl">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">Batch Import</div>
                <CardTitle className="mt-2">批量导入简历并打分</CardTitle>
                <CardDescription>
                  保留现有 Word / PDF 解析、PaddleOCR fallback 与评分流程，只把导入体验单独整理成一条更清晰的工作流。
                </CardDescription>
              </div>
              <Button asChild variant="secondary">
                <a href="/hr/phase2">
                  管理 JD评分卡
                  <ArrowRight className="size-4" />
                </a>
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-5">
            {!importableScorecards.length ? (
              <EmptyState
                title="暂无可导入评分卡"
                description="先去 JD评分卡 创建支持批量导入的评分卡，再回来导入简历。"
                actionLabel="前往 JD评分卡"
                onAction={() => {
                  window.location.href = "/hr/phase2";
                }}
              />
            ) : (
              <>
                <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="space-y-2">
                    <Label>导入评分卡</Label>
                    <NativeSelect value={importScorecardId} onChange={(event) => setImportScorecardId(event.target.value)}>
                      <option value="">选择评分卡</option>
                      {importableScorecards.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                  <div className="space-y-2">
                    <Label>批次名称</Label>
                    <Input
                      value={batchName}
                      placeholder="例如：3月前端导入批次"
                      onChange={(event) => setBatchName(event.target.value)}
                    />
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <ImportMeta label="当前评分卡" value={selectedScorecard?.name || "未选择"} />
                  <ImportMeta label="Schema" value={selectedScorecard?.schema_version || "phase2_scorecard_v1"} subdued />
                  <ImportMeta label="更新时间" value={selectedScorecard?.updated_at || "尚未保存"} subdued />
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.doc,.docx"
                  multiple
                  className="hidden"
                  onChange={(event) => setSelectedFiles(Array.from(event.target.files || []))}
                />

                <div className="surface-muted p-5">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-base font-semibold tracking-[-0.03em] text-slate-950">待导入文件</div>
                      <p className="mt-1 text-sm leading-6 text-slate-500">
                        支持 `pdf / doc / docx`。扫描版 PDF 会自动尝试 OCR，导入完成后可直接回看批次结果。
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
                        <FileUp className="size-4" />
                        选择文件
                      </Button>
                      <Button onClick={importFiles} disabled={isImporting}>
                        {isImporting ? "导入中..." : "开始导入"}
                      </Button>
                    </div>
                  </div>

                  <div className="mt-5">
                    {!selectedFiles.length ? (
                      <div className="rounded-[22px] border border-dashed border-black/[0.08] bg-white/56 px-4 py-6 text-sm text-slate-500">
                        尚未选择文件。建议先选定评分卡，再一次性导入同一批次简历。
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {selectedFiles.map((file) => (
                          <Badge key={`${file.name}-${file.size}`} variant="neutral">
                            {file.name}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <StatusBanner
                  title="导入状态"
                  description={importStatus}
                  tone={statusToneFromMessage(importStatus)}
                  loading={isImporting}
                />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">Recent Batches</div>
                <CardTitle className="mt-2">导入批次</CardTitle>
                <CardDescription>最近导入批次统一收在这里，便于持续切换查看结果与统计。</CardDescription>
              </div>
              <Button variant="secondary" size="sm" onClick={() => void loadBatches(currentBatchId)}>
                <RefreshCcw className="size-4" />
                刷新
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {!batches.length ? (
              <EmptyState
                title={isLoadingBatches ? "批次加载中..." : "暂无导入批次"}
                description="完成第一次简历导入后，最近批次会显示在这里。"
              />
            ) : (
              <ScrollArea className="h-[520px] pr-1">
                <div className="space-y-3">
                  {batches.map((batch) => (
                    <button
                      key={batch.id}
                      type="button"
                      onClick={() => void loadBatchDetail(batch.id)}
                      className={cn(
                        "w-full rounded-[26px] border px-5 py-4 text-left transition-all duration-200",
                        currentBatchId === batch.id
                          ? "border-slate-950 bg-slate-950 text-white shadow-[0_22px_46px_-28px_rgba(15,23,42,0.7)]"
                          : "border-black/[0.06] bg-white/72 hover:-translate-y-0.5 hover:bg-white",
                      )}
                    >
                      <div className="text-base font-semibold tracking-[-0.03em]">
                        {batch.batch_name || batch.scorecard_name || batch.id}
                      </div>
                      <div className={cn("mt-2 text-sm", currentBatchId === batch.id ? "text-slate-300" : "text-slate-500")}>
                        {batch.scorecard_name || "-"} · {batch.created_at || "-"}
                      </div>
                      <div className={cn("mt-1 text-sm", currentBatchId === batch.id ? "text-slate-300" : "text-slate-500")}>
                        {batch.processed_files || 0} / {batch.total_files || 0} 已处理
                      </div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-end 2xl:justify-between">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">Batch Results</div>
              <CardTitle className="mt-2">批次结果</CardTitle>
              <CardDescription>
                当前批次：{currentBatch?.batch_name || currentBatchId || "暂无"}。结果区保留安静的对比表格，便于 HR 快速比较候选人。
              </CardDescription>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4 2xl:min-w-[760px]">
              <ImportMeta label="总文件数" value={summaryBatch.total_files || 0} />
              <ImportMeta label="已处理" value={summaryBatch.processed_files || 0} subdued />
              <ImportMeta label="建议沟通" value={summaryBatch.recommend_count || 0} />
              <ImportMeta label="继续复核" value={summaryBatch.review_count || 0} subdued />
            </div>
          </div>
        </CardHeader>

        <CardContent className="pb-8 md:pb-10">
          {!batchResults.length ? (
            <EmptyState
              title="当前批次暂无结果"
              description="选择一个已有批次，或完成新的导入后再查看结果。"
            />
          ) : (
            <div className="overflow-hidden rounded-[30px] border border-black/[0.06] bg-white/76">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>候选人 / 文件</TableHead>
                    <TableHead>命中项</TableHead>
                    <TableHead className="w-[160px]">评分</TableHead>
                    <TableHead>筛选结论</TableHead>
                    <TableHead className="w-[140px] text-right">详情</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {batchResults.map((item) => (
                    <TableRow key={`${item.resume_profile_id}-${item.filename}`}>
                      <TableCell>
                        <div className="space-y-2">
                          <div className="text-base font-semibold tracking-[-0.03em] text-slate-950">
                            {item.extracted_name || "未识别姓名"}
                          </div>
                          <div className="text-sm leading-6 text-slate-500">
                            {item.filename || "-"}
                            <br />
                            {item.location || "-"} · {item.parse_status || "-"}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          {(item.matched_terms || []).slice(0, 4).map((term) => (
                            <Badge key={`${item.filename}-${term}`} variant="success">
                              {term}
                            </Badge>
                          ))}
                          {(item.missing_terms || []).slice(0, 4).map((term) => (
                            <Badge key={`${item.filename}-missing-${term}`} variant="warn">
                              缺：{term}
                            </Badge>
                          ))}
                          {!item.matched_terms?.length && !item.missing_terms?.length ? (
                            <Badge variant="neutral">暂无关键词摘要</Badge>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-[28px] font-semibold tracking-[-0.05em] text-slate-950">
                          {formatScore(item.total_score)}
                        </div>
                        <div className="mt-1 text-sm text-slate-500">
                          {item.years_experience || "-"} 年 · {item.education_level || "-"}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={decisionVariant(item.decision)}>{decisionLabel(item.decision)}</Badge>
                        <div className="mt-3 text-sm leading-7 text-slate-600">
                          {(item.hard_filter_fail_reasons || []).join("；") || item.summary || "暂无摘要"}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        {item.resume_profile_id ? (
                          <a
                            className="inline-flex rounded-full border border-black/[0.08] bg-black/[0.02] px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-black/[0.04] hover:text-slate-950"
                            href={`/api/v3/candidates/${encodeURIComponent(item.resume_profile_id)}/search-profile`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Profile JSON
                          </a>
                        ) : (
                          <span className="text-sm text-slate-400">无 Profile</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
