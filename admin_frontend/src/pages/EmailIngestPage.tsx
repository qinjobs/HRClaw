import { useEffect, useMemo, useState } from "react";
import { History, PlayCircle, RefreshCcw, Save, Timer } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { StatTile } from "@/components/shared/stat-tile";
import { StatusBanner } from "@/components/shared/status-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { getJson, postJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import { formatDecision, formatScore, formatTime } from "@/lib/format";
import type { EmailIngestRecord, HrUser, Phase2ScorecardRecord } from "@/lib/types";

interface HrUsersResponse {
  items: HrUser[];
}

interface ScorecardsResponse {
  items: Phase2ScorecardRecord[];
}

interface RecordsResponse {
  items: EmailIngestRecord[];
}

interface RunOnceResult {
  ok: boolean;
  result?: {
    scan_directory?: string;
    scanned_files?: number;
    new_files?: number;
    duplicate_files?: number;
    processed_files?: number;
    recommend_count?: number;
    review_count?: number;
    reject_count?: number;
    failed_count?: number;
  };
}

export function EmailIngestPage() {
  const bootstrap = getBootstrap();
  const { pushToast } = useToast();
  const isAdmin = bootstrap.userRole === "admin";

  const [users, setUsers] = useState<HrUser[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [scorecards, setScorecards] = useState<Phase2ScorecardRecord[]>([]);
  const [records, setRecords] = useState<EmailIngestRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [statusMessage, setStatusMessage] = useState("准备就绪，可先配置参数再执行立即采集。");
  const [maxFiles, setMaxFiles] = useState("20");

  const [enabled, setEnabled] = useState(false);
  const [scorecardId, setScorecardId] = useState("");
  const [intervalMinutes, setIntervalMinutes] = useState("60");
  const [ingestDirectory, setIngestDirectory] = useState("");

  const selectedUser = useMemo(
    () => users.find((item) => item.id === selectedUserId) ?? null,
    [users, selectedUserId],
  );
  const importableScorecards = useMemo(
    () => (scorecards || []).filter((item) => item.supports_resume_import),
    [scorecards],
  );

  const stats = useMemo(() => {
    const completed = records.filter((item) => item.status === "completed").length;
    const failed = records.filter((item) => item.status === "failed").length;
    const processing = records.filter((item) => item.status === "processing").length;
    return { total: records.length, completed, failed, processing };
  }, [records]);

  const syncFormFromUser = (user: HrUser | null) => {
    if (!user) {
      setEnabled(false);
      setScorecardId("");
      setIntervalMinutes("60");
      setIngestDirectory("");
      return;
    }
    setEnabled(Boolean(user.email_ingest_enabled));
    setScorecardId(String(user.default_scorecard_id || ""));
    setIntervalMinutes(String(user.email_ingest_interval_minutes || 60));
    setIngestDirectory(String(user.email_ingest_directory || ""));
  };

  const loadUsers = async (preserve = true) => {
    const payload = await getJson<HrUsersResponse>("/api/email-ingest/users");
    const items = payload.items || [];
    setUsers(items);
    setSelectedUserId((current) => {
      if (preserve && current && items.some((item) => item.id === current)) {
        return current;
      }
      return items[0]?.id || "";
    });
  };

  const loadScorecards = async () => {
    const payload = await getJson<ScorecardsResponse>("/api/v2/scorecards");
    setScorecards(payload.items || []);
  };

  const loadRecords = async (userId: string) => {
    if (!userId) {
      setRecords([]);
      return;
    }
    const payload = await getJson<RecordsResponse>(`/api/email-ingest/records?user_id=${encodeURIComponent(userId)}&limit=100`);
    setRecords(payload.items || []);
  };

  const reloadAll = async (preserve = true) => {
    setLoading(true);
    try {
      await Promise.all([loadUsers(preserve), loadScorecards()]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reloadAll(false);
  }, []);

  useEffect(() => {
    syncFormFromUser(selectedUser);
    if (selectedUser?.id) {
      void loadRecords(selectedUser.id);
    } else {
      setRecords([]);
    }
  }, [selectedUser?.id]);

  const saveConfig = async () => {
    if (!selectedUserId) return;
    setSaving(true);
    try {
      const payload = {
        email_ingest_enabled: enabled,
        default_scorecard_id: scorecardId,
        email_ingest_interval_minutes: Number(intervalMinutes || 60),
        email_ingest_directory: ingestDirectory.trim(),
      };
      await postJson(`/api/email-ingest/users/${encodeURIComponent(selectedUserId)}/config`, payload);
      setStatusMessage("配置已保存。");
      await reloadAll();
      pushToast({ tone: "success", title: "保存成功", description: "自动采集配置已更新。" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setStatusMessage(`保存失败：${message}`);
      pushToast({ tone: "error", title: "保存失败", description: message });
    } finally {
      setSaving(false);
    }
  };

  const runOnce = async () => {
    if (!selectedUserId) return;
    setRunning(true);
    setStatusMessage("正在执行立即采集与打分...");
    try {
      const result = await postJson<RunOnceResult>("/api/email-ingest/run-once", {
        user_id: selectedUserId,
        trigger: "manual_ui",
        max_files: Number(maxFiles || 20),
        ingest_directory: ingestDirectory.trim() || undefined,
      });
      await loadRecords(selectedUserId);
      const summary = result.result || {};
      setStatusMessage(
        `执行完成：目录 ${summary.scan_directory || "-"}；扫描 ${summary.scanned_files || 0}，新增 ${summary.new_files || 0}，处理 ${summary.processed_files || 0}，重复 ${summary.duplicate_files || 0}。`,
      );
      pushToast({ tone: "success", title: "立即采集完成" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "执行失败";
      setStatusMessage(`执行失败：${message}`);
      pushToast({ tone: "error", title: "执行失败", description: message });
    } finally {
      setRunning(false);
    }
  };

  const retryFailed = async () => {
    if (!selectedUserId) return;
    setRetrying(true);
    try {
      const result = await postJson<{ retried?: number; succeeded?: number; failed?: number }>("/api/email-ingest/retry-failed", {
        user_id: selectedUserId,
        max_retry: 3,
        limit: 50,
      });
      await loadRecords(selectedUserId);
      setStatusMessage(`失败重试完成：重试 ${result.retried || 0}，成功 ${result.succeeded || 0}，失败 ${result.failed || 0}。`);
      pushToast({ tone: "success", title: "失败重试完成" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "重试失败";
      setStatusMessage(`重试失败：${message}`);
      pushToast({ tone: "error", title: "重试失败", description: message });
    } finally {
      setRetrying(false);
    }
  };

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="邮箱自动采集"
    >
      <section className="grid gap-4 md:grid-cols-4">
        <StatTile label="采集记录" value={stats.total} hint="最近 100 条记录" />
        <StatTile label="处理成功" value={stats.completed} hint="status=completed" />
        <StatTile label="处理失败" value={stats.failed} hint="status=failed" />
        <StatTile label="处理中" value={stats.processing} hint="status=processing" />
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>自动采集配置</CardTitle>
            <CardDescription>按用户维度管理：是否开启自动采集、默认评分卡、采集目录与时间间隔。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="ingest-user">管理用户</Label>
                <NativeSelect
                  id="ingest-user"
                  value={selectedUserId}
                  disabled={!users.length || loading || !isAdmin}
                  onChange={(event) => setSelectedUserId(event.target.value)}
                >
                  {users.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name || item.username} ({item.username})
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ingest-scorecard">JD 评分卡</Label>
                <NativeSelect
                  id="ingest-scorecard"
                  value={scorecardId}
                  onChange={(event) => setScorecardId(event.target.value)}
                >
                  <option value="">请选择评分卡</option>
                  {importableScorecards.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ingest-interval">自动采集间隔（分钟）</Label>
                <Input
                  id="ingest-interval"
                  type="number"
                  min="5"
                  max="1440"
                  value={intervalMinutes}
                  onChange={(event) => setIntervalMinutes(event.target.value)}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="ingest-directory">采集目录</Label>
                <Input
                  id="ingest-directory"
                  placeholder="/data/email/{user_id} 或 /Users/.../data/email/admin"
                  value={ingestDirectory}
                  onChange={(event) => setIngestDirectory(event.target.value)}
                />
                <div className="text-xs text-slate-500">
                  留空时默认扫描 <code>SCREENING_EMAIL_RESUME_ROOT/&lt;user_id&gt;/YYYYMMDD</code>；支持使用 <code>{"{user_id}"}</code> 占位符。
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-2xl border border-black/[0.08] bg-black/[0.02] px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">开启自动采集</div>
                <div className="text-xs text-slate-500">开启后会按配置间隔定时扫描并自动打分。</div>
              </div>
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </div>

            <div className="flex flex-wrap gap-3">
              <Button onClick={saveConfig} disabled={saving || !selectedUserId}>
                <Save className="size-4" />
                {saving ? "保存中..." : "保存配置"}
              </Button>
              <Button variant="secondary" onClick={() => void reloadAll()} disabled={loading}>
                <RefreshCcw className="size-4" />
                {loading ? "刷新中..." : "刷新配置"}
              </Button>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-black/[0.08] bg-white/80 px-4 py-3 text-sm">
                <div className="text-slate-500">上次执行</div>
                <div className="mt-1 font-medium text-slate-900">{formatTime(selectedUser?.email_ingest_last_run_at)}</div>
              </div>
              <div className="rounded-2xl border border-black/[0.08] bg-white/80 px-4 py-3 text-sm">
                <div className="text-slate-500">下次执行</div>
                <div className="mt-1 font-medium text-slate-900">{formatTime(selectedUser?.email_ingest_next_run_at)}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>手工执行</CardTitle>
            <CardDescription>用于上线验收或临时补跑：立即采集、失败重试。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="max-files">本次最大处理文件数</Label>
              <Input
                id="max-files"
                type="number"
                min="1"
                max="500"
                value={maxFiles}
                onChange={(event) => setMaxFiles(event.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={runOnce} disabled={running || !selectedUserId}>
                <PlayCircle className="size-4" />
                {running ? "执行中..." : "立即采集并打分"}
              </Button>
              <Button variant="secondary" onClick={retryFailed} disabled={retrying || !selectedUserId}>
                <Timer className="size-4" />
                {retrying ? "重试中..." : "重试失败记录"}
              </Button>
            </div>
            <StatusBanner title="执行状态" description={statusMessage} tone="default" loading={running || retrying} />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>采集记录</CardTitle>
            <CardDescription>显示该用户最近处理记录，含状态、分数与错误信息。</CardDescription>
          </div>
          <Button variant="secondary" onClick={() => selectedUserId && void loadRecords(selectedUserId)} disabled={!selectedUserId}>
            <History className="size-4" />
            刷新记录
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文件</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>决策</TableHead>
                <TableHead>分数</TableHead>
                <TableHead>更新时间</TableHead>
                <TableHead>错误信息</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.length ? (
                records.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      {item.id && item.file_name ? (
                        <a
                          href={`/api/email-ingest/records/${encodeURIComponent(item.id)}/file`}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-slate-900 underline-offset-2 hover:underline"
                          title="点击查看原始简历文件"
                        >
                          {item.file_name}
                        </a>
                      ) : (
                        <div className="font-medium text-slate-900">{item.file_name || "-"}</div>
                      )}
                      <div className="text-xs text-slate-500">{item.source_date || "-"}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={item.status === "completed" ? "success" : item.status === "failed" ? "danger" : "warn"}>
                        {item.status || "-"}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDecision(item.decision)}</TableCell>
                    <TableCell>{formatScore(item.total_score)}</TableCell>
                    <TableCell>{formatTime(item.updated_at)}</TableCell>
                    <TableCell className="max-w-[320px] truncate text-xs text-slate-500">{item.error || "-"}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-slate-500">
                    暂无采集记录
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </AppShell>
  );
}
