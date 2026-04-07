import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ClipboardCheck, FileUp, PlayCircle, Sparkles } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { PageSection } from "@/components/shared/page-section";
import { StatTile } from "@/components/shared/stat-tile";
import { StatusBanner } from "@/components/shared/status-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { getJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import type { Phase2ScorecardRecord } from "@/lib/types";

type LaunchCardProps = {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  actionLabel: string;
  href: string;
  badge?: string;
};

function LaunchCard({ icon: Icon, title, description, actionLabel, href, badge }: LaunchCardProps) {
  return (
    <div className="rounded-xl bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#0071e3] text-white">
            <Icon className="size-5" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[21px] font-semibold leading-[1.19] tracking-[-0.03em] text-[#1d1d1f]">{title}</h3>
              {badge ? <Badge variant="neutral">{badge}</Badge> : null}
            </div>
            <p className="mt-2 text-[15px] leading-[1.47] tracking-[-0.022em] text-black/68">{description}</p>
          </div>
        </div>
      </div>
      <div className="mt-5">
        <Button asChild className="w-full justify-center">
          <a href={href}>
            {actionLabel}
            <ArrowRight className="size-4" />
          </a>
        </Button>
      </div>
    </div>
  );
}

export function TrialHubPage() {
  const bootstrap = getBootstrap();
  const [scorecards, setScorecards] = useState<Phase2ScorecardRecord[]>([]);
  const [selectedScorecardId, setSelectedScorecardId] = useState("");
  const [loadingScorecards, setLoadingScorecards] = useState(true);

  useEffect(() => {
    const loadScorecards = async () => {
      try {
        const data = await getJson<{ items: Phase2ScorecardRecord[] }>("/api/v2/scorecards");
        const items = data.items || [];
        setScorecards(items);
        const preferred = items.find((item) => item.supports_resume_import) || null;
        setSelectedScorecardId(preferred?.id || "");
      } catch {
        setScorecards([]);
        setSelectedScorecardId("");
      } finally {
        setLoadingScorecards(false);
      }
    };

    void loadScorecards();
  }, []);

  const importableScorecards = useMemo(
    () => scorecards.filter((item) => item.supports_resume_import),
    [scorecards],
  );

  const selectedScorecard = useMemo(() => {
    if (!selectedScorecardId) {
      return importableScorecards[0] || null;
    }
    return importableScorecards.find((item) => item.id === selectedScorecardId) || importableScorecards[0] || null;
  }, [importableScorecards, selectedScorecardId]);

  const resumeImportHref = selectedScorecard
    ? `/hr/resume-imports?scorecardId=${encodeURIComponent(selectedScorecard.id)}`
    : "/hr/resume-imports";

  const trialSteps = [
    {
      step: "01",
      title: "先定标准",
      body: "从 JD 评分卡开始，先把岗位的硬条件、加分项和阈值定下来。",
    },
    {
      step: "02",
      title: "再做导入",
      body: "上传 5 到 20 份 PDF 简历，确认解析、打分和证据是否稳定。",
    },
    {
      step: "03",
      title: "需要时再装插件",
      body: "Chrome 插件只负责浏览器采集层，不改变后台评分逻辑。",
    },
    {
      step: "04",
      title: "最后做校准",
      body: "用 20 到 50 份历史样本调阈值，再决定是否进入下一阶段。",
    },
  ];

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="试点中心"
      subtitle="把 JD 评分卡、PDF 简历导入和 Chrome 浏览器采集收拢在一页。建议先用 1 个岗位、1 个 HR、20 到 50 份历史简历跑通闭环。"
    >
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatTile label="试点路径" value="2 条" hint="手工导入 / 浏览器采集" />
        <StatTile label="主入口" value="JD评分卡" hint="先定标准，再做简历打分" />
        <StatTile label="插件层" value="Chrome" hint="BOSS 页面详情页快照入库" />
        <StatTile label="建议规模" value="1 岗位" hint="20-50 份历史简历" />
      </section>

      <section className="grid gap-8 xl:grid-cols-[minmax(0,1.14fr)_380px]">
        <div className="space-y-8">
          <Card className="overflow-hidden bg-black text-white shadow-none">
            <CardHeader className="space-y-4 pb-5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="info">MVP 起点</Badge>
                <Badge className="border-white/18 bg-white/8 text-white/72" variant="neutral">手工导入</Badge>
                <Badge className="border-white/18 bg-white/8 text-white/72" variant="neutral">浏览器采集</Badge>
              </div>
              <div>
                <CardTitle className="text-[56px] leading-[1.07] text-white">从这里开始试点</CardTitle>
                <CardDescription className="mt-3 max-w-3xl text-[17px] leading-[1.47] text-white/72">
                  先把一个岗位的标准和两条简历入口收拢到一页。HR 只需要在这里决定：先生成评分卡，还是直接导入简历。
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 lg:grid-cols-3">
                <LaunchCard
                  icon={Sparkles}
                  title="JD 评分卡"
                  description="把岗位 JD 变成统一的筛选标准、阈值和面试题。"
                  actionLabel="生成 / 调整评分卡"
                  href="/hr/phase2"
                  badge="起点"
                />
                <LaunchCard
                  icon={FileUp}
                  title="简历导入"
                  description="上传 PDF / Word 简历，批量打分并回看批次结果。"
                  actionLabel="开始批量导入"
                  href={resumeImportHref}
                  badge={selectedScorecard ? selectedScorecard.name : "需先选评分卡"}
                />
                <LaunchCard
                  icon={PlayCircle}
                  title="任务执行"
                  description="检查 BOSS 会话、执行推荐采集，并把结果回写到清单。"
                  actionLabel="检查插件会话"
                  href="/hr/tasks"
                  badge="浏览器采集层"
                />
              </div>

              <div className="grid gap-5 rounded-xl bg-white p-6 text-[#1d1d1f] lg:grid-cols-[minmax(0,1fr)_320px]">
                <div className="space-y-4">
                  <div className="text-[21px] font-semibold leading-[1.19] tracking-[-0.03em] text-[#1d1d1f]">选择试点评分卡</div>
                  <p className="text-[15px] leading-[1.47] tracking-[-0.022em] text-black/68">
                    先选一个支持简历导入的评分卡。没有评分卡时，先去 JD 评分卡页生成一份再回来导入。
                  </p>
                  <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                    <div className="space-y-2">
                      <Label>评分卡</Label>
                      <NativeSelect
                        value={selectedScorecardId}
                        onChange={(event) => setSelectedScorecardId(event.target.value)}
                      >
                        <option value="">选择支持导入的评分卡</option>
                        {importableScorecards.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        onClick={() => {
                          window.location.href = resumeImportHref;
                        }}
                        disabled={!selectedScorecard || loadingScorecards}
                      >
                        开始导入
                      </Button>
                      <Button asChild variant="secondary">
                        <a href="/hr/phase2">生成评分卡</a>
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="grid gap-3">
                  <div className="rounded-[12px] bg-[#f5f5f7] px-4 py-3">
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-black/45">可导入评分卡</div>
                    <div className="mt-2 text-[34px] font-semibold leading-[1.07] tracking-[-0.04em] text-[#1d1d1f]">
                      {loadingScorecards ? "加载中..." : importableScorecards.length}
                    </div>
                  </div>
                  <div className="rounded-[12px] bg-[#f5f5f7] px-4 py-3">
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-black/45">当前选择</div>
                    <div className="mt-2 text-[15px] font-semibold tracking-[-0.022em] text-[#1d1d1f]">
                      {selectedScorecard?.name || "未选择"}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <PageSection
            title="试点顺序"
            description="建议按标准、导入、采集、校准的顺序推进。这样更容易在一周内拿到能验证的结果。"
          >
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
              {trialSteps.map((item) => (
                <div key={item.step} className="rounded-xl bg-white p-5">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-black/42">{item.step}</div>
                  <div className="mt-3 text-[21px] font-semibold leading-[1.19] tracking-[-0.03em] text-[#1d1d1f]">{item.title}</div>
                  <p className="mt-2 text-[15px] leading-[1.47] tracking-[-0.022em] text-black/68">{item.body}</p>
                </div>
              ))}
            </div>
          </PageSection>
        </div>

        <div className="space-y-6">
          <StatusBanner
            tone="success"
            title="试点建议"
            description="只验证一个岗位族，先用测试工程师最稳。不要同时开多个岗位，也不要一开始就碰 BOSS 自动抓取。"
          />

          <Card>
            <CardHeader>
              <CardTitle>Chrome 插件采集层</CardTitle>
              <CardDescription>插件负责浏览器侧快照和同步，不改变后台评分逻辑。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-[15px] leading-[1.47] text-black/68">
              <div className="rounded-[12px] bg-[#f5f5f7] p-4">
                <div className="font-medium text-slate-950">1. 安装插件</div>
                <p className="mt-1">把 `chrome_extensions/boss_resume_score` 当作浏览器采集层安装到 Chrome。</p>
              </div>
              <div className="rounded-[12px] bg-[#f5f5f7] p-4">
                <div className="font-medium text-slate-950">2. 打开候选人详情</div>
                <p className="mt-1">在 BOSS 的候选人详情页刷新一次，让插件完成同步和采集。</p>
              </div>
              <div className="rounded-[12px] bg-[#f5f5f7] p-4">
                <div className="font-medium text-slate-950">3. 回到任务执行</div>
                <p className="mt-1">点击“检查插件会话”，确认本地系统已经看到当前登录状态。</p>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button asChild size="sm">
                  <a href="/hr/tasks">检查会话</a>
                </Button>
                <Button asChild size="sm" variant="secondary">
                  <a href="/hr/workbench">打开处理台</a>
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>试点边界</CardTitle>
              <CardDescription>这些能力先不进 MVP，避免试点期把价值主线稀释掉。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-[15px] leading-[1.47] text-black/68">
              {[
                "BOSS session 自动抓取",
                "ATS 同步",
                "自动打招呼",
                "多岗位工作流",
                "复杂报表",
              ].map((item) => (
                <div key={item} className="flex items-center gap-3 rounded-[12px] bg-[#f5f5f7] px-4 py-3">
                  <ClipboardCheck className="size-4 text-black/35" />
                  <span>{item}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>
    </AppShell>
  );
}
