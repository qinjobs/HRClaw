from __future__ import annotations


def phase2_page_html(username: str) -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>JD管理 - JD评分卡与批量导入</title>
  <style>
    :root {
      --ink: #19314f;
      --muted: #6c7f96;
      --line: #d6e0ea;
      --soft: rgba(255,255,255,.78);
      --panel: rgba(255,255,255,.9);
      --bg: radial-gradient(1200px 420px at -5% -10%, rgba(255, 213, 179, .6), transparent 60%),
            radial-gradient(1000px 360px at 110% -20%, rgba(142, 214, 255, .48), transparent 58%),
            linear-gradient(180deg, #fff6ed 0%, #eef7ff 54%, #f6fbff 100%);
      --brand: #ff7a18;
      --brand-deep: #ff4d4d;
      --accent: #1d9bf0;
      --ok: #17a36b;
      --warn: #f59e0b;
      --bad: #dc2626;
      --shadow: 0 24px 60px rgba(40, 63, 96, .12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    .top {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 22px;
      background: rgba(255,255,255,.62);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(255,255,255,.7);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 20px;
      font-weight: 700;
    }
    .brandMark {
      width: 38px;
      height: 38px;
      border-radius: 14px;
      background: linear-gradient(145deg, var(--brand), var(--brand-deep));
      box-shadow: 0 18px 32px rgba(255, 122, 24, .24);
    }
    .topNav {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .navGroup {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.74);
      border: 1px solid rgba(210, 224, 239, .9);
    }
    .navLabel {
      font-size: 12px;
      color: var(--muted);
    }
    .top a,
    .top button {
      color: var(--ink);
      text-decoration: none;
      background: #fff;
      border: 1px solid #dbe6f2;
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 12px;
      cursor: pointer;
    }
    .wrap {
      width: min(100%, 1820px);
      margin: 18px auto 0;
      padding: 0 16px 20px;
    }
    .shell {
      display: grid;
      grid-template-columns: 460px minmax(0, 1fr);
      gap: 18px;
      min-height: calc(100vh - 116px);
    }
    .panel {
      background: var(--panel);
      border: 1px solid rgba(255,255,255,.75);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      overflow: hidden;
    }
    .builder {
      display: flex;
      flex-direction: column;
    }
    .panelInner {
      padding: 24px;
    }
    .hero {
      padding: 24px 24px 18px;
      background: linear-gradient(145deg, rgba(255, 122, 24, .15), rgba(29, 155, 240, .06));
      border-bottom: 1px solid rgba(221, 231, 242, .9);
    }
    h1, h2, h3 { margin: 0; }
    .title {
      font-size: 26px;
      line-height: 1.08;
      font-weight: 700;
    }
    .sub {
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }
    .sectionTitle {
      margin-bottom: 12px;
      font-size: 16px;
      font-weight: 700;
    }
    .field,
    .fieldWide {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field label,
    .fieldWide label,
    .grid label,
    .toggles label {
      font-size: 12px;
      color: var(--muted);
    }
    input, select, textarea, button {
      font: inherit;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 11px 13px;
      background: rgba(255,255,255,.94);
      color: var(--ink);
    }
    textarea {
      min-height: 96px;
      resize: vertical;
      line-height: 1.5;
    }
    .jdInput {
      min-height: 180px;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .threeGrid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .weightGrid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .toggles {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
      margin-top: 6px;
    }
    .toggleItem {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }
    .metaBox {
      margin-top: 14px;
      border-radius: 16px;
      background: #10233c;
      color: #dce9ff;
      padding: 14px;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      min-height: 120px;
    }
    .btnRow {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 16px;
    }
    .primaryBtn,
    .secondaryBtn,
    .ghostBtn,
    .miniBtn {
      border-radius: 14px;
      cursor: pointer;
      border: 0;
      padding: 11px 16px;
    }
    .primaryBtn {
      color: #fff;
      background: linear-gradient(120deg, var(--brand-deep), var(--brand));
      box-shadow: 0 14px 28px rgba(255, 103, 56, .22);
    }
    .secondaryBtn {
      color: #fff;
      background: linear-gradient(120deg, #138fe2, #29b6f6);
    }
    .ghostBtn, .miniBtn {
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
    }
    .resultTop {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 24px;
      border-bottom: 1px solid rgba(218, 229, 241, .9);
      background: linear-gradient(145deg, rgba(29, 155, 240, .06), rgba(255, 122, 24, .08));
    }
    .resultTitle {
      font-size: 22px;
      font-weight: 700;
    }
    .statusBadge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,.82);
      border: 1px solid #dce7f3;
      color: var(--muted);
      font-size: 12px;
    }
    .resultBody {
      padding: 20px 24px 24px;
    }
    .batchToolbar {
      display: grid;
      grid-template-columns: 1.1fr 1fr auto auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 14px;
    }
    .batchList {
      display: flex;
      gap: 10px;
      overflow: auto;
      padding-bottom: 6px;
      margin-bottom: 16px;
    }
    .batchChip {
      min-width: 220px;
      padding: 12px 14px;
      border-radius: 18px;
      border: 1px solid #dbe6f2;
      background: #fff;
      cursor: pointer;
    }
    .batchChip.active {
      border-color: #ffb16d;
      box-shadow: 0 10px 24px rgba(255, 122, 24, .14);
      background: linear-gradient(145deg, rgba(255, 247, 239, .94), #fff);
    }
    .batchName {
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .batchMeta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .summaryBar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .summaryCard {
      min-width: 120px;
      padding: 12px 14px;
      border-radius: 18px;
      background: #fff;
      border: 1px solid #dbe6f2;
    }
    .summaryCard strong {
      display: block;
      font-size: 22px;
      margin-top: 4px;
    }
    .tableWrap {
      overflow: auto;
      border: 1px solid #dbe6f2;
      border-radius: 18px;
      background: #fff;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }
    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid #ebf0f5;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #f8fbfe;
      z-index: 1;
      color: var(--muted);
      font-weight: 600;
    }
    .decision {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      color: #fff;
    }
    .decision.recommend { background: var(--ok); }
    .decision.review { background: var(--warn); }
    .decision.reject { background: var(--bad); }
    .miniList {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .miniTag {
      display: inline-flex;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      background: #f6f8fb;
      border: 1px solid #e3ebf3;
    }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }
    .empty {
      padding: 40px 18px;
      text-align: center;
      color: var(--muted);
    }
    .hidden {
      display: none;
    }
    @media (max-width: 1080px) {
      .shell { grid-template-columns: 1fr; }
      .batchToolbar { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .grid, .threeGrid, .weightGrid, .toggles { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="top">
    <div class="brand">
      <div class="brandMark"></div>
      <div>招聘智能筛选平台 · JD管理</div>
    </div>
    <div class="topNav">
      <span>用户：__USERNAME__</span>
      <div class="navGroup">
        <span class="navLabel">流程</span>
        <a href="/hr/tasks">任务执行</a>
        <a href="/hr/workbench">推荐处理台</a>
        <a href="/hr/checklist">Checklist</a>
      </div>
      <div class="navGroup">
        <span class="navLabel">搜索</span>
        <a href="/hr/search">高级搜索</a>
      </div>
      <div class="navGroup">
        <span class="navLabel">当前页</span>
        <a href="/hr/phase2">JD评分卡</a>
      </div>
      <button id="logoutBtn" type="button">退出</button>
    </div>
  </div>

  <div class="wrap">
    <div class="shell">
      <section class="panel builder">
        <div class="hero">
          <h1 class="title">JD 生成评分卡</h1>
          <div class="sub">先让系统从 HR 提供的 JD 生成一版初始规则，再由你调整必备项、加分项、阈值和硬过滤条件。保存后即可直接用于批量简历筛查。</div>
        </div>
        <div class="panelInner">
          <div class="toolbar">
            <select id="scorecardSelect"></select>
            <button id="newScorecardBtn" class="ghostBtn" type="button">新建评分卡</button>
          </div>

          <div class="grid">
            <div class="field">
              <label>评分卡名称</label>
              <input id="scorecardName" placeholder="例如：Python开发工程师-北京" />
            </div>
            <div class="field">
              <label>角色标题</label>
              <input id="roleTitle" placeholder="例如：Python开发工程师" />
            </div>
          </div>

          <div class="fieldWide" style="margin-top:12px;">
            <label>JD 原文</label>
            <textarea id="jdText" class="jdInput" placeholder="把 HR 提供的 JD 整段贴进来，点击“根据JD生成初稿”。"></textarea>
          </div>

          <div class="btnRow">
            <button id="generateBtn" class="secondaryBtn" type="button">根据 JD 生成初稿</button>
            <button id="saveBtn" class="primaryBtn" type="button">保存评分卡</button>
          </div>

          <div style="margin-top:18px;">
            <div class="sectionTitle">筛选条件</div>
            <div class="threeGrid">
              <div class="field">
                <label>城市</label>
                <input id="filterLocation" placeholder="北京" />
              </div>
              <div class="field">
                <label>最低年限</label>
                <input id="filterYearsMin" type="number" min="0" max="30" step="0.5" placeholder="3" />
              </div>
              <div class="field">
                <label>最低学历</label>
                <select id="filterEducationMin">
                  <option value="">不限</option>
                  <option value="大专">大专</option>
                  <option value="本科">本科</option>
                  <option value="硕士">硕士</option>
                  <option value="博士">博士</option>
                </select>
              </div>
            </div>
          </div>

          <div class="grid" style="margin-top:18px;">
            <div class="fieldWide">
              <label>必备项（每行一个）</label>
              <textarea id="mustHave"></textarea>
            </div>
            <div class="fieldWide">
              <label>加分项（每行一个）</label>
              <textarea id="niceToHave"></textarea>
            </div>
            <div class="fieldWide">
              <label>排除项（每行一个）</label>
              <textarea id="exclude"></textarea>
            </div>
            <div class="fieldWide">
              <label>岗位关键词 / 标题（每行一个）</label>
              <textarea id="titles"></textarea>
            </div>
            <div class="fieldWide">
              <label>行业关键词（每行一个）</label>
              <textarea id="industry"></textarea>
            </div>
            <div class="fieldWide">
              <label>备注</label>
              <textarea id="summary" placeholder="说明这个评分卡适用的业务背景、特殊边界或人工判断标准。"></textarea>
            </div>
          </div>

          <div style="margin-top:18px;">
            <div class="sectionTitle">权重与阈值</div>
            <div class="weightGrid">
              <div class="field"><label>核心技能权重</label><input id="weightMustHave" type="number" min="0" step="1" /></div>
              <div class="field"><label>加分项权重</label><input id="weightNiceToHave" type="number" min="0" step="1" /></div>
              <div class="field"><label>岗位标题权重</label><input id="weightTitleMatch" type="number" min="0" step="1" /></div>
              <div class="field"><label>行业匹配权重</label><input id="weightIndustryMatch" type="number" min="0" step="1" /></div>
              <div class="field"><label>经验权重</label><input id="weightExperience" type="number" min="0" step="1" /></div>
              <div class="field"><label>学历权重</label><input id="weightEducation" type="number" min="0" step="1" /></div>
              <div class="field"><label>城市权重</label><input id="weightLocation" type="number" min="0" step="1" /></div>
              <div class="field"><label>Recommend 阈值</label><input id="thresholdRecommend" type="number" min="0" max="100" step="1" /></div>
              <div class="field"><label>Review 阈值</label><input id="thresholdReview" type="number" min="0" max="100" step="1" /></div>
              <div class="field"><label>核心技能最低命中率</label><input id="mustHaveRatioMin" type="number" min="0" max="1" step="0.1" /></div>
            </div>
          </div>

          <div style="margin-top:18px;">
            <div class="sectionTitle">硬过滤开关</div>
            <div class="toggles">
              <label class="toggleItem"><input id="enforceYears" type="checkbox" /> 年限必须满足</label>
              <label class="toggleItem"><input id="enforceEducation" type="checkbox" /> 学历必须满足</label>
              <label class="toggleItem"><input id="enforceLocation" type="checkbox" /> 地点必须满足</label>
              <label class="toggleItem"><input id="strictExclude" type="checkbox" /> 命中排除项直接淘汰</label>
            </div>
          </div>

          <div id="builderMeta" class="metaBox">等待操作...</div>
        </div>
      </section>

      <section class="panel">
        <div class="resultTop">
          <div>
            <div class="resultTitle">批量导入简历并打分</div>
            <div class="sub" style="margin-top:6px;">支持 Word / PDF，多文件一次导入。系统会先抽文本，再按照选中的评分卡给出“建议沟通 / 继续复核 / 暂不沟通”。</div>
          </div>
          <div id="importStatus" class="statusBadge">等待导入</div>
        </div>
        <div class="resultBody">
          <div class="batchToolbar">
            <div class="field">
              <label>用于筛查的评分卡</label>
              <select id="importScorecardSelect"></select>
            </div>
            <div class="field">
              <label>批次名称</label>
              <input id="batchName" placeholder="例如：3月22日-后端简历首轮筛查" />
            </div>
            <button id="pickFilesBtn" class="ghostBtn" type="button">选择文件</button>
            <button id="importBtn" class="primaryBtn" type="button">开始导入</button>
          </div>
          <input id="fileInput" class="hidden" type="file" accept=".pdf,.doc,.docx" multiple />
          <div class="mono" id="selectedFiles" style="margin-bottom:16px; color: var(--muted);">尚未选择文件。</div>

          <div class="sectionTitle">最近批次</div>
          <div id="batchList" class="batchList"></div>

          <div id="batchSummary" class="summaryBar"></div>

          <div class="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>文件</th>
                  <th>候选人</th>
                  <th>评分结果</th>
                  <th>经验 / 学历 / 地点</th>
                  <th>命中 / 缺口</th>
                  <th>理由</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody id="resultRows">
                <tr><td class="empty" colspan="7">先保存评分卡，再选择简历文件开始导入。</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const state = {
      currentScorecardId: null,
      currentBatchId: null,
      scorecards: [],
      batches: [],
      selectedFiles: [],
    };

    const scorecardSelect = document.getElementById("scorecardSelect");
    const importScorecardSelect = document.getElementById("importScorecardSelect");
    const builderMeta = document.getElementById("builderMeta");
    const batchList = document.getElementById("batchList");
    const batchSummary = document.getElementById("batchSummary");
    const resultRows = document.getElementById("resultRows");
    const fileInput = document.getElementById("fileInput");
    const selectedFiles = document.getElementById("selectedFiles");
    const importStatus = document.getElementById("importStatus");

    function esc(value) {
      if (value === null || value === undefined) return "";
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function linesToArray(value) {
      return String(value || "")
        .split(/\\r?\\n/)
        .map((item) => item.trim())
        .filter(Boolean);
    }

    function arrayToLines(values) {
      return (values || []).join("\\n");
    }

    function setBuilderMeta(message, payload = null) {
      builderMeta.textContent = payload ? `${message}\\n\\n${JSON.stringify(payload, null, 2)}` : message;
    }

    async function getJson(path) {
      const res = await fetch(path);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `请求失败(${res.status})`);
      return data;
    }

    async function postJson(path, payload) {
      const res = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload || {})
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `请求失败(${res.status})`);
      return data;
    }

    function collectScorecardPayload() {
      return {
        id: state.currentScorecardId,
        name: document.getElementById("scorecardName").value.trim(),
        scorecard: {
          schema_version: "phase2_scorecard_v1",
          name: document.getElementById("scorecardName").value.trim(),
          role_title: document.getElementById("roleTitle").value.trim(),
          jd_text: document.getElementById("jdText").value.trim(),
          summary: document.getElementById("summary").value.trim(),
          filters: {
            location: document.getElementById("filterLocation").value.trim() || null,
            years_min: document.getElementById("filterYearsMin").value.trim() ? Number(document.getElementById("filterYearsMin").value) : null,
            education_min: document.getElementById("filterEducationMin").value || null,
          },
          must_have: linesToArray(document.getElementById("mustHave").value),
          nice_to_have: linesToArray(document.getElementById("niceToHave").value),
          exclude: linesToArray(document.getElementById("exclude").value),
          titles: linesToArray(document.getElementById("titles").value),
          industry: linesToArray(document.getElementById("industry").value),
          weights: {
            must_have: Number(document.getElementById("weightMustHave").value || 0),
            nice_to_have: Number(document.getElementById("weightNiceToHave").value || 0),
            title_match: Number(document.getElementById("weightTitleMatch").value || 0),
            industry_match: Number(document.getElementById("weightIndustryMatch").value || 0),
            experience: Number(document.getElementById("weightExperience").value || 0),
            education: Number(document.getElementById("weightEducation").value || 0),
            location: Number(document.getElementById("weightLocation").value || 0),
          },
          thresholds: {
            recommend_min: Number(document.getElementById("thresholdRecommend").value || 0),
            review_min: Number(document.getElementById("thresholdReview").value || 0),
          },
          hard_filters: {
            enforce_years: document.getElementById("enforceYears").checked,
            enforce_education: document.getElementById("enforceEducation").checked,
            enforce_location: document.getElementById("enforceLocation").checked,
            strict_exclude: document.getElementById("strictExclude").checked,
            must_have_ratio_min: Number(document.getElementById("mustHaveRatioMin").value || 0),
          }
        }
      };
    }

    function fillScorecardForm(record) {
      const scorecard = (record && record.scorecard) || record || {};
      state.currentScorecardId = record && record.id ? record.id : null;
      document.getElementById("scorecardName").value = scorecard.name || record?.name || "";
      document.getElementById("roleTitle").value = scorecard.role_title || "";
      document.getElementById("jdText").value = scorecard.jd_text || record?.jd_text || "";
      document.getElementById("summary").value = scorecard.summary || "";
      document.getElementById("filterLocation").value = scorecard.filters?.location || "";
      document.getElementById("filterYearsMin").value = scorecard.filters?.years_min ?? "";
      document.getElementById("filterEducationMin").value = scorecard.filters?.education_min || "";
      document.getElementById("mustHave").value = arrayToLines(scorecard.must_have);
      document.getElementById("niceToHave").value = arrayToLines(scorecard.nice_to_have);
      document.getElementById("exclude").value = arrayToLines(scorecard.exclude);
      document.getElementById("titles").value = arrayToLines(scorecard.titles);
      document.getElementById("industry").value = arrayToLines(scorecard.industry);
      document.getElementById("weightMustHave").value = scorecard.weights?.must_have ?? 42;
      document.getElementById("weightNiceToHave").value = scorecard.weights?.nice_to_have ?? 12;
      document.getElementById("weightTitleMatch").value = scorecard.weights?.title_match ?? 12;
      document.getElementById("weightIndustryMatch").value = scorecard.weights?.industry_match ?? 8;
      document.getElementById("weightExperience").value = scorecard.weights?.experience ?? 14;
      document.getElementById("weightEducation").value = scorecard.weights?.education ?? 7;
      document.getElementById("weightLocation").value = scorecard.weights?.location ?? 5;
      document.getElementById("thresholdRecommend").value = scorecard.thresholds?.recommend_min ?? 75;
      document.getElementById("thresholdReview").value = scorecard.thresholds?.review_min ?? 55;
      document.getElementById("mustHaveRatioMin").value = scorecard.hard_filters?.must_have_ratio_min ?? 0.5;
      document.getElementById("enforceYears").checked = Boolean(scorecard.hard_filters?.enforce_years);
      document.getElementById("enforceEducation").checked = Boolean(scorecard.hard_filters?.enforce_education);
      document.getElementById("enforceLocation").checked = Boolean(scorecard.hard_filters?.enforce_location);
      document.getElementById("strictExclude").checked = Boolean(scorecard.hard_filters?.strict_exclude);
      setBuilderMeta("评分卡已载入。", scorecard);
    }

    function resetScorecardForm() {
      state.currentScorecardId = null;
      fillScorecardForm({
        scorecard: {
          name: "",
          role_title: "",
          jd_text: "",
          summary: "",
          filters: {location: "", years_min: "", education_min: ""},
          must_have: [],
          nice_to_have: [],
          exclude: [],
          titles: [],
          industry: [],
          weights: {must_have: 42, nice_to_have: 12, title_match: 12, industry_match: 8, experience: 14, education: 7, location: 5},
          thresholds: {recommend_min: 75, review_min: 55},
          hard_filters: {enforce_years: false, enforce_education: false, enforce_location: false, strict_exclude: false, must_have_ratio_min: 0.5}
        }
      });
      setBuilderMeta("已切换为新建模式。先贴 JD，再生成评分卡。");
    }

    function renderScorecardOptions() {
      const options = state.scorecards.map((item) => `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join("");
      scorecardSelect.innerHTML = `<option value="">选择已有评分卡</option>${options}`;
      importScorecardSelect.innerHTML = `<option value="">选择评分卡</option>${options}`;
      if (state.currentScorecardId) {
        scorecardSelect.value = state.currentScorecardId;
        importScorecardSelect.value = state.currentScorecardId;
      }
    }

    async function loadScorecards(preferredId = null) {
      const data = await getJson("/api/v2/scorecards");
      state.scorecards = data.items || [];
      if (preferredId) state.currentScorecardId = preferredId;
      renderScorecardOptions();
      if (preferredId) {
        const found = state.scorecards.find((item) => item.id === preferredId);
        if (found) fillScorecardForm(found);
      } else if (!state.currentScorecardId && state.scorecards.length) {
        fillScorecardForm(state.scorecards[0]);
        renderScorecardOptions();
      } else if (!state.scorecards.length) {
        resetScorecardForm();
      }
    }

    async function generateScorecard() {
      const jdText = document.getElementById("jdText").value.trim();
      if (!jdText) {
        setBuilderMeta("请先贴入 JD 原文。");
        return;
      }
      const payload = await postJson("/api/v2/scorecards/generate", {
        jd_text: jdText,
        name: document.getElementById("scorecardName").value.trim() || document.getElementById("roleTitle").value.trim() || undefined
      });
      fillScorecardForm({scorecard: payload.scorecard});
      setBuilderMeta("已根据 JD 生成初始评分卡，请确认后保存。", payload.scorecard);
    }

    async function saveScorecard() {
      const payload = collectScorecardPayload();
      const data = await postJson("/api/v2/scorecards", payload);
      state.currentScorecardId = data.item.id;
      await loadScorecards(data.item.id);
      setBuilderMeta(`评分卡已保存：${data.item.name}`, data.item.scorecard);
    }

    function renderBatchSummary(batch) {
      if (!batch) {
        batchSummary.innerHTML = "";
        return;
      }
      batchSummary.innerHTML = `
        <div class="summaryCard">总文件数<strong>${esc(batch.total_files || 0)}</strong></div>
        <div class="summaryCard">已处理<strong>${esc(batch.processed_files || 0)}</strong></div>
        <div class="summaryCard">建议沟通<strong>${esc(batch.recommend_count || 0)}</strong></div>
        <div class="summaryCard">继续复核<strong>${esc(batch.review_count || 0)}</strong></div>
        <div class="summaryCard">暂不沟通<strong>${esc(batch.reject_count || 0)}</strong></div>
      `;
    }

    function renderResults(items) {
      if (!items || !items.length) {
        resultRows.innerHTML = '<tr><td class="empty" colspan="7">当前批次暂无结果。</td></tr>';
        return;
      }
      resultRows.innerHTML = items.map((item) => {
        const profileLink = item.resume_profile_id ? `/api/v3/candidates/${encodeURIComponent(item.resume_profile_id)}/search-profile` : "";
        return `
          <tr>
            <td><strong>${esc(item.filename || "-")}</strong><br/><span class="mono">${esc(item.parse_status || "-")}</span></td>
            <td>${esc(item.extracted_name || "未识别")}<br/><span class="mono">${esc(item.location || "-")}</span></td>
            <td><span class="decision ${esc(item.decision || "review")}">${esc(item.decision || "-")}</span><br/><strong>${item.total_score === null || item.total_score === undefined ? "-" : esc(Number(item.total_score).toFixed(2))} 分</strong></td>
            <td>${esc(item.years_experience || "-")} 年<br/>${esc(item.education_level || "-")}<br/>${esc(item.location || "-")}</td>
            <td>
              <div class="miniList">${(item.matched_terms || []).slice(0, 4).map((term) => `<span class="miniTag">${esc(term)}</span>`).join("") || '<span class="miniTag">无命中</span>'}</div>
              <div class="miniList" style="margin-top:6px;">${(item.missing_terms || []).slice(0, 4).map((term) => `<span class="miniTag" style="border-color:#ffd5d5;background:#fff7f7;">缺：${esc(term)}</span>`).join("")}</div>
            </td>
            <td>${esc((item.hard_filter_fail_reasons || []).join("；") || item.summary || "-")}</td>
            <td>${profileLink ? `<a target="_blank" href="${esc(profileLink)}">Profile JSON</a>` : "-"}<br/><span class="mono">${esc(item.resume_profile_id || "")}</span></td>
          </tr>
        `;
      }).join("");
    }

    function renderBatchList() {
      if (!state.batches.length) {
        batchList.innerHTML = '<div class="batchChip"><div class="batchName">暂无导入批次</div><div class="batchMeta">保存评分卡并导入简历后，最近批次会显示在这里。</div></div>';
        return;
      }
      batchList.innerHTML = state.batches.map((batch) => `
        <button class="batchChip ${batch.id === state.currentBatchId ? "active" : ""}" type="button" data-batch-id="${esc(batch.id)}">
          <div class="batchName">${esc(batch.batch_name || batch.scorecard_name || batch.id)}</div>
          <div class="batchMeta">${esc(batch.scorecard_name || "-")}<br/>${esc(batch.created_at || "-")}<br/>${esc(batch.processed_files || 0)} / ${esc(batch.total_files || 0)} 已处理</div>
        </button>
      `).join("");
    }

    async function loadBatches(preferredId = null) {
      const data = await getJson("/api/v2/resume-imports");
      state.batches = data.items || [];
      if (preferredId) state.currentBatchId = preferredId;
      if (!state.currentBatchId && state.batches.length) state.currentBatchId = state.batches[0].id;
      renderBatchList();
      if (state.currentBatchId) {
        await loadBatchDetail(state.currentBatchId);
      } else {
        renderBatchSummary(null);
        renderResults([]);
      }
    }

    async function loadBatchDetail(batchId) {
      state.currentBatchId = batchId;
      renderBatchList();
      const data = await getJson(`/api/v2/resume-imports/${encodeURIComponent(batchId)}`);
      renderBatchSummary(data.batch || null);
      renderResults(data.results || []);
      importStatus.textContent = `当前批次：${(data.batch || {}).batch_name || batchId}`;
    }

    function readFileAsBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = String(reader.result || "");
          const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
          resolve({name: file.name, size: file.size, content_base64: base64});
        };
        reader.onerror = () => reject(reader.error || new Error("文件读取失败"));
        reader.readAsDataURL(file);
      });
    }

    async function importFiles() {
      const scorecardId = importScorecardSelect.value || state.currentScorecardId;
      if (!scorecardId) {
        importStatus.textContent = "请先选择评分卡";
        return;
      }
      if (!state.selectedFiles.length) {
        importStatus.textContent = "请先选择文件";
        return;
      }
      importStatus.textContent = "正在读取文件并导入...";
      const files = await Promise.all(state.selectedFiles.map((file) => readFileAsBase64(file)));
      const data = await postJson("/api/v2/resume-imports", {
        scorecard_id: scorecardId,
        batch_name: document.getElementById("batchName").value.trim(),
        created_by: "hr_ui",
        files
      });
      state.selectedFiles = [];
      fileInput.value = "";
      selectedFiles.textContent = "导入完成。";
      await loadBatches(data.batch.id);
      importStatus.textContent = `导入完成：${data.batch.batch_name || data.batch.id}`;
    }

    scorecardSelect.addEventListener("change", () => {
      const item = state.scorecards.find((entry) => entry.id === scorecardSelect.value);
      if (!item) return;
      fillScorecardForm(item);
      importScorecardSelect.value = item.id;
    });
    importScorecardSelect.addEventListener("change", () => {
      if (importScorecardSelect.value) state.currentScorecardId = importScorecardSelect.value;
    });
    document.getElementById("newScorecardBtn").addEventListener("click", resetScorecardForm);
    document.getElementById("generateBtn").addEventListener("click", () => {
      generateScorecard().catch((err) => setBuilderMeta(`生成失败：${err.message}`));
    });
    document.getElementById("saveBtn").addEventListener("click", () => {
      saveScorecard().catch((err) => setBuilderMeta(`保存失败：${err.message}`));
    });
    document.getElementById("pickFilesBtn").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
      state.selectedFiles = Array.from(fileInput.files || []);
      selectedFiles.textContent = state.selectedFiles.length
        ? `已选择 ${state.selectedFiles.length} 个文件：${state.selectedFiles.map((file) => file.name).join("，")}`
        : "尚未选择文件。";
    });
    document.getElementById("importBtn").addEventListener("click", () => {
      importFiles().catch((err) => {
        importStatus.textContent = `导入失败：${err.message}`;
      });
    });
    batchList.addEventListener("click", (event) => {
      const target = event.target.closest("[data-batch-id]");
      if (!target) return;
      const batchId = target.getAttribute("data-batch-id");
      if (!batchId) return;
      loadBatchDetail(batchId).catch((err) => {
        importStatus.textContent = `加载批次失败：${err.message}`;
      });
    });
    document.getElementById("logoutBtn").addEventListener("click", async () => {
      try {
        await postJson("/api/logout", {});
      } catch (_) {}
      window.location.href = "/login";
    });

    Promise.all([loadScorecards(), loadBatches()]).catch((err) => {
      setBuilderMeta(`初始化失败：${err.message}`);
      importStatus.textContent = `初始化失败：${err.message}`;
    });
  </script>
</body>
</html>""".replace("__USERNAME__", username)
