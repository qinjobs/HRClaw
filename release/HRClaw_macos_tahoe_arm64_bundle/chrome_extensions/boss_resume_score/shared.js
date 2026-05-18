(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BossResumeScoreShared = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const DETAIL_ROOT_SELECTORS = [
    ".resume-detail-wrap",
    ".geek-resume-wrap",
    ".card-content",
    ".iboss-left",
    ".card-inner",
    "main"
  ];

  const HINT_SELECTORS = [
    ".name-label",
    ".candidate-head .name",
    ".geek-name",
    ".resume-top-wrap .name",
    "h1",
    "h2",
    ".name"
  ];

  const DETAIL_KEYWORDS = [
    "工作经历",
    "项目经历",
    "教育经历",
    "自我评价",
    "打招呼",
    "期望职位",
    "测试工程师",
    "在线简历"
  ];
  const SIMILAR_SECTION_TITLES = [
    "其他相似经历的牛人"
  ];
  const CANDIDATE_NAME_BLOCKLIST = new Set([
    "打招呼",
    "工作经历",
    "项目经历",
    "教育经历",
    "经历概览",
    "最近关注",
    "期望职位",
    "测试工程师",
    "测试开发",
    "刚刚活跃",
    "今日活跃",
    "在线",
    "活跃",
    "热搜",
    "本科",
    "硕士",
    "博士",
    "大专",
    "专科",
    "院校",
    "职位",
    "经历",
    "公司",
    "面议"
  ]);
  const CANDIDATE_NAME_NOISE_TOKENS = [
    "!function",
    "createelement(\"script\")",
    "createelement('script')",
    "nomodule",
    "document",
    "window.",
    "webpack",
    "vite",
    "<script",
    "function(",
    "=>"
  ];
  const QA_TOOL_TOKENS = [
    "linux", "shell", "adb", "charles", "fiddler", "postman", "jmeter", "metersphere",
    "pytest", "selenium", "appium", "mysql", "oracle", "sqlserver", "sql server",
    "数据库", "api", "接口测试", "jira", "tapd", "ones", "yapi", "swagger", "docker", "xmind"
  ];
  const QA_ROLE_TOKENS = [
    "测试工程师", "软件测试", "测试开发", "qa", "quality assurance", "自动化测试", "功能测试"
  ];
  const QA_PROCESS_VERBS = [
    "测试", "编写", "设计", "执行", "跟踪", "分析", "复现", "验证", "回归", "review", "execute", "track", "debug"
  ];
  const QA_PROCESS_ARTIFACTS = [
    "用例", "test case", "case", "测试计划", "缺陷", "bug", "报告", "接口测试", "功能测试", "自动化测试", "jira", "禅道"
  ];
  const PYTHON_CORE_TOKENS = ["python", "pycharm", "fastapi", "flask", "django"];
  const PYTHON_RUNTIME_TOKENS = ["linux", "shell", "docker", "redis", "kafka", "elasticsearch", "mysql"];
  const CAPTION_QC_TOKENS = ["视频", "图像", "caption", "文案", "写作", "标注", "审美", "影视", "构图", "镜头"];
  const ZHENGZHOU_TOKENS = ["郑州", "河南"];

  const JOB_OPTIONS_FALLBACK = [
    { id: "qa_test_engineer_v1", name: "QA Test Engineer" },
    { id: "py_dev_engineer_v1", name: "Python Engineer" },
    { id: "caption_aesthetic_qc_v1", name: "Caption Aesthetic QC" },
    { id: "caption_ai_trainer_zhengzhou_v1", name: "Caption AI Trainer (Zhengzhou)" }
  ];
  const JOB_NAME_MAP = {
    qa_test_engineer_v1: "测试工程师",
    py_dev_engineer_v1: "Python 开发工程师",
    caption_aesthetic_qc_v1: "文案审美质检",
    caption_ai_trainer_zhengzhou_v1: "郑州 Caption AI 训练师"
  };
  const DECISION_LABELS = {
    recommend: "推荐",
    review: "待复核",
    reject: "不推荐",
    pending: "待处理"
  };
  const PIPELINE_STAGE_LABELS = {
    new: "新入库",
    scored: "已评分",
    to_review: "待复核",
    to_contact: "建议沟通",
    contacted: "已沟通",
    awaiting_reply: "待回复",
    needs_followup: "待跟进",
    interview_invited: "已邀约",
    interview_scheduled: "面试已约",
    talent_pool: "人才库",
    rejected: "已淘汰",
    do_not_contact: "不再联系"
  };
  const PIPELINE_STAGE_OPTIONS = [
    "new",
    "scored",
    "to_review",
    "to_contact",
    "contacted",
    "awaiting_reply",
    "needs_followup",
    "interview_invited",
    "interview_scheduled",
    "talent_pool",
    "rejected",
    "do_not_contact"
  ];
  const SOURCE_LABELS = {
    boss_extension: "插件入库",
    pipeline: "任务采集"
  };
  const PREFS_STORAGE_KEY = "boss_resume_score_prefs";
  const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8080";
  const ERROR_LABELS = {
    candidate_detail_not_found: "未识别到候选人详情页",
    boss_tab_not_found: "当前没有打开 BOSS 页面",
    unsupported_message: "插件消息类型不支持",
    extension_score_failed: "打分请求失败",
    job_id_required: "请选择岗位评分卡",
    candidate_detail_missing: "当前页面缺少可打分的简历内容",
    candidate_stage_save_failed: "保存候选人状态失败",
    candidate_sync_failed: "候选人入库失败"
  };
  const DIMENSION_LABELS = {
    core_test_depth: "测试深度",
    tools_coverage: "工具覆盖度",
    frontend_backend: "前后端覆盖",
    defect_closure: "缺陷闭环",
    industry_fit: "行业匹配",
    analysis_logic: "分析逻辑",
    experience_maturity: "经验成熟度",
    python_engineering: "Python 工程能力",
    linux_shell: "Linux/Shell",
    java_support: "Java 协作能力",
    middleware_stack: "中间件栈",
    security_fit: "安全匹配度",
    analysis_design: "分析设计",
    aesthetic_writing: "文案审美",
    film_art_theory: "影视理论",
    ai_annotation_qc: "AI 标注质检",
    visual_domain_coverage: "视觉领域覆盖",
    watching_volume: "观片量",
    english: "英文能力",
    portfolio: "作品集",
    gender_bonus: "特殊加权",
    writing_naturalness: "文笔自然度",
    reading_rule_follow: "规则遵循",
    visual_analysis: "视觉分析",
    film_language: "影视语言",
    output_stability: "输出稳定性",
    ai_annotation_experience: "AI 标注经验",
    long_term_stability: "长期稳定性"
  };

  function normalizeText(value) {
    return String(value || "")
      .replace(/\r\n?/g, "\n")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]{2,}/g, " ")
      .trim();
  }

  function shortText(value, maxLength) {
    const text = normalizeText(value);
    if (!text || text.length <= maxLength) {
      return text;
    }
    return text.slice(0, Math.max(0, maxLength - 1)).trimEnd() + "...";
  }

  function hashText(value) {
    const text = String(value || "");
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  function buildCandidateKey(context) {
    const pageTextDigest = hashText(normalizeText((context && context.pageText) || ""));
    const payload = [
      String((context && context.pageUrl) || "").split("#")[0],
      shortText((context && context.candidateName) || "", 80),
      shortText((context && context.candidateHint) || "", 120),
      shortText((context && context.pageTitle) || "", 120),
      pageTextDigest
    ].join("\n");
    return hashText(payload);
  }

  function normalizeCandidateNameText(value) {
    return normalizeText(value).replace(/[♂♀]/g, "").trim();
  }

  function extractCandidateNameFragment(value) {
    const normalized = normalizeCandidateNameText(value);
    if (!normalized) {
      return "";
    }
    const lowered = normalized.toLowerCase();
    if (normalized.length > 80 || CANDIDATE_NAME_NOISE_TOKENS.some(function (token) { return lowered.includes(token); })) {
      return "";
    }
    const leadingMatch = normalized.match(/^([\u4e00-\u9fa5·*]{2,8})(?:\s|$|[\/|｜-])/);
    if (leadingMatch && !CANDIDATE_NAME_BLOCKLIST.has(leadingMatch[1])) {
      return leadingMatch[1];
    }
    const matches = normalized.match(/[\u4e00-\u9fa5·*]{2,8}/g) || [];
    for (const entry of matches) {
      if (!CANDIDATE_NAME_BLOCKLIST.has(entry)) {
        return entry;
      }
    }
    return "";
  }

  function looksLikeCandidateName(value) {
    return Boolean(extractCandidateNameFragment(value));
  }

  function normalizeBackendBaseUrl(value) {
    let raw = normalizeText(value);
    if (!raw) {
      return DEFAULT_BACKEND_BASE_URL;
    }
    if (!/^https?:\/\//i.test(raw)) {
      raw = "http://" + raw;
    }
    try {
      const parsed = new URL(raw);
      if (!/^https?:$/i.test(parsed.protocol) || !parsed.hostname) {
        return "";
      }
      return parsed.origin.replace(/\/+$/, "");
    } catch (error) {
      return "";
    }
  }

  function parseCnNumber(token) {
    const map = {
      "零": 0,
      "一": 1,
      "二": 2,
      "两": 2,
      "三": 3,
      "四": 4,
      "五": 5,
      "六": 6,
      "七": 7,
      "八": 8,
      "九": 9
    };
    const raw = normalizeText(token);
    if (!raw) {
      return null;
    }
    if (/^\d+(?:\.\d+)?$/.test(raw)) {
      return Number(raw);
    }
    if (raw === "十") {
      return 10;
    }
    if (raw.includes("十")) {
      const parts = raw.split("十");
      const tens = parts[0] ? map[parts[0]] : 1;
      const ones = parts[1] ? map[parts[1]] : 0;
      if (tens === undefined || ones === undefined) {
        return null;
      }
      return tens * 10 + ones;
    }
    return map[raw] !== undefined ? map[raw] : null;
  }

  function extractYearsExperience(text) {
    const raw = String(text || "");
    const patterns = [
      /(?:工作经验|工作年限|测试经验|软件测试经验|开发或测试经验)\s*[:：]?\s*([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年/gi,
      /([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年(?:工作)?经验/gi,
      /([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年以上/gi,
      /([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年\s*[+＋]/gi,
      /([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年(?=\s*(?:本科|硕士|博士|大专|专科|在职|离职|月内到岗|随时到岗))/gi
    ];
    const values = [];
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(raw))) {
        const value = parseCnNumber(match[1]);
        if (value !== null && value >= 0 && value <= 40) {
          values.push(value);
        }
      }
    }
    return values.length ? Math.max.apply(null, values) : null;
  }

  function extractEducationLevel(text) {
    const raw = String(text || "").toLowerCase();
    if (/博士|phd/.test(raw)) {
      return "phd";
    }
    if (/硕士|master|研究生/.test(raw)) {
      return "master";
    }
    if (/本科|bachelor|学士/.test(raw)) {
      return "bachelor";
    }
    if (/大专|专科|college/.test(raw)) {
      return "college";
    }
    return "";
  }

  function findTokenHits(text, tokens) {
    const lowered = String(text || "").toLowerCase();
    return (tokens || []).filter(function (token) {
      return lowered.includes(String(token || "").toLowerCase());
    });
  }

  function pickEvidenceLines(text, tokens, limit) {
    const loweredTokens = (tokens || []).map(function (token) { return String(token || "").toLowerCase(); });
    if (!loweredTokens.length) {
      return [];
    }
    const lines = normalizeText(text).split("\n").map(function (line) { return line.trim(); }).filter(Boolean);
    const seen = new Set();
    const picked = [];
    for (const line of lines) {
      const lowered = line.toLowerCase();
      if (line.length < 6 || CANDIDATE_NAME_NOISE_TOKENS.some(function (token) { return lowered.includes(token); })) {
        continue;
      }
      if (!loweredTokens.some(function (token) { return lowered.includes(token); })) {
        continue;
      }
      if (seen.has(line)) {
        continue;
      }
      seen.add(line);
      picked.push(shortText(line, 80));
      if (picked.length >= (limit || 3)) {
        break;
      }
    }
    return picked;
  }

  function summarizeQuickFit(label, matched, missing) {
    if (label === "基本符合") {
      return matched.length ? "已命中核心 JD 条件，可优先关注这些证据。" : "已满足核心条件。";
    }
    if (label === "部分符合") {
      return missing.length ? "命中了一部分 JD 要点，但还需要补充核查缺口。" : "需要再人工复核。";
    }
    return missing.length ? "当前主要卡在这些硬条件或核心证据上。" : "暂未命中核心 JD 要点。";
  }

  function analyzeQaQuickFit(pageText) {
    const text = normalizeText(pageText);
    const years = extractYearsExperience(text);
    const education = extractEducationLevel(text);
    const roleHits = findTokenHits(text, QA_ROLE_TOKENS);
    const toolHits = findTokenHits(text, QA_TOOL_TOKENS);
    const verbHits = findTokenHits(text, QA_PROCESS_VERBS);
    const artifactHits = findTokenHits(text, QA_PROCESS_ARTIFACTS);
    const hasTestingEvidence = roleHits.length > 0 || (verbHits.length > 0 && artifactHits.length > 0);
    const degreeOk = ["bachelor", "master", "phd"].includes(education);
    const yearsOk = years !== null && years >= 3;
    const toolsOk = toolHits.length >= 2;
    const matched = [];
    const missing = [];
    if (degreeOk) {
      matched.push("本科及以上学历");
    } else {
      missing.push("学历未达到本科");
    }
    if (yearsOk) {
      matched.push((years || 0) + " 年测试/开发经验");
    } else {
      missing.push("测试/开发经验少于 3 年");
    }
    if (hasTestingEvidence) {
      matched.push("命中测试流程/用例/缺陷/回归等核心证据");
    } else {
      missing.push("缺少测试流程闭环证据");
    }
    if (toolsOk) {
      matched.push("命中工具链：" + toolHits.slice(0, 4).join(" / "));
    } else {
      missing.push("工具链证据偏少");
    }
    const mustHits = [degreeOk, yearsOk, hasTestingEvidence].filter(Boolean).length;
    const label = mustHits === 3 && toolsOk ? "基本符合" : mustHits >= 2 ? "部分符合" : "明显不符";
    const tone = label === "基本符合" ? "good" : label === "部分符合" ? "warn" : "bad";
    return {
      label: label,
      tone: tone,
      matched: matched,
      missing: missing,
      evidenceLines: pickEvidenceLines(text, roleHits.concat(toolHits).concat(verbHits).concat(artifactHits), 4),
      summary: summarizeQuickFit(label, matched, missing)
    };
  }

  function analyzePythonQuickFit(pageText) {
    const text = normalizeText(pageText);
    const years = extractYearsExperience(text);
    const education = extractEducationLevel(text);
    const pythonHits = findTokenHits(text, PYTHON_CORE_TOKENS);
    const runtimeHits = findTokenHits(text, PYTHON_RUNTIME_TOKENS);
    const degreeOk = ["bachelor", "master", "phd"].includes(education);
    const yearsOk = years !== null && years >= 3;
    const pythonOk = pythonHits.length > 0;
    const linuxOk = runtimeHits.some(function (token) { return ["linux", "shell", "docker"].includes(token.toLowerCase()); });
    const matched = [];
    const missing = [];
    if (degreeOk) {
      matched.push("本科及以上学历");
    } else {
      missing.push("学历未达到本科");
    }
    if (yearsOk) {
      matched.push((years || 0) + " 年开发经验");
    } else {
      missing.push("开发经验少于 3 年");
    }
    if (pythonOk) {
      matched.push("命中 Python 技术栈");
    } else {
      missing.push("缺少 Python 直接证据");
    }
    if (linuxOk) {
      matched.push("命中 Linux/Shell 环境经验");
    } else {
      missing.push("缺少 Linux/Shell 证据");
    }
    if (runtimeHits.length > 1) {
      matched.push("命中运行环境：" + runtimeHits.slice(0, 4).join(" / "));
    }
    const mustHits = [degreeOk, yearsOk, pythonOk, linuxOk].filter(Boolean).length;
    const label = mustHits >= 4 ? "基本符合" : mustHits >= 3 ? "部分符合" : "明显不符";
    const tone = label === "基本符合" ? "good" : label === "部分符合" ? "warn" : "bad";
    return {
      label: label,
      tone: tone,
      matched: matched,
      missing: missing,
      evidenceLines: pickEvidenceLines(text, pythonHits.concat(runtimeHits), 4),
      summary: summarizeQuickFit(label, matched, missing)
    };
  }

  function analyzeCaptionQcQuickFit(pageText) {
    const text = normalizeText(pageText);
    const education = extractEducationLevel(text);
    const hits = findTokenHits(text, CAPTION_QC_TOKENS);
    const matched = [];
    const missing = [];
    if (education) {
      matched.push("已识别出学历信息");
    } else {
      missing.push("学历信息不明显");
    }
    if (hits.length >= 3) {
      matched.push("命中内容审美/标注相关关键词");
    } else {
      missing.push("内容审美/标注关键词偏少");
    }
    const label = hits.length >= 3 ? "基本符合" : hits.length >= 2 ? "部分符合" : "明显不符";
    const tone = label === "基本符合" ? "good" : label === "部分符合" ? "warn" : "bad";
    return {
      label: label,
      tone: tone,
      matched: matched,
      missing: missing,
      evidenceLines: pickEvidenceLines(text, hits, 4),
      summary: summarizeQuickFit(label, matched, missing)
    };
  }

  function analyzeCaptionZhengzhouQuickFit(pageText) {
    const text = normalizeText(pageText);
    const years = extractYearsExperience(text);
    const education = extractEducationLevel(text);
    const hits = findTokenHits(text, CAPTION_QC_TOKENS.concat(ZHENGZHOU_TOKENS));
    const cityOk = findTokenHits(text, ZHENGZHOU_TOKENS).length > 0;
    const educationOk = Boolean(education);
    const matched = [];
    const missing = [];
    if (cityOk) {
      matched.push("命中郑州/河南相关意向");
    } else {
      missing.push("未看到郑州意向");
    }
    if (educationOk) {
      matched.push("已识别出教育信息");
    } else {
      missing.push("教育信息不明确");
    }
    if (years !== null && years >= 1) {
      matched.push((years || 0) + " 年相关经历");
    }
    if (hits.length >= 3) {
      matched.push("命中内容理解/标注关键词");
    } else {
      missing.push("内容理解/标注关键词偏少");
    }
    const mustHits = [cityOk, educationOk, hits.length >= 3].filter(Boolean).length;
    const label = mustHits >= 3 ? "基本符合" : mustHits >= 2 ? "部分符合" : "明显不符";
    const tone = label === "基本符合" ? "good" : label === "部分符合" ? "warn" : "bad";
    return {
      label: label,
      tone: tone,
      matched: matched,
      missing: missing,
      evidenceLines: pickEvidenceLines(text, hits, 4),
      summary: summarizeQuickFit(label, matched, missing)
    };
  }

  function analyzeGenericQuickFit(pageText) {
    const text = normalizeText(pageText);
    const years = extractYearsExperience(text);
    const education = extractEducationLevel(text);
    const commonHits = findTokenHits(text, QA_TOOL_TOKENS.concat(PYTHON_CORE_TOKENS, PYTHON_RUNTIME_TOKENS, CAPTION_QC_TOKENS));
    const matched = [];
    const missing = [];
    const degreeOk = Boolean(education);
    const yearsOk = years !== null && years >= 1;
    const detailOk = commonHits.length >= 2 || /工作经历|项目经历|教育经历|技能|专业技能/.test(text);
    if (degreeOk) {
      matched.push("已识别出学历信息");
    } else {
      missing.push("学历信息不明显");
    }
    if (yearsOk) {
      matched.push((years || 0) + " 年相关经验");
    } else {
      missing.push("工作年限信息偏少");
    }
    if (detailOk) {
      matched.push("简历正文信息较完整");
    } else {
      missing.push("简历正文关键信息不足");
    }
    if (commonHits.length) {
      matched.push("命中关键词：" + commonHits.slice(0, 4).join(" / "));
    }
    const hitCount = [degreeOk, yearsOk, detailOk].filter(Boolean).length;
    const label = hitCount >= 3 ? "基本符合" : hitCount >= 2 ? "部分符合" : "明显不符";
    const tone = label === "基本符合" ? "good" : label === "部分符合" ? "warn" : "bad";
    return {
      label: label,
      tone: tone,
      matched: matched,
      missing: missing,
      evidenceLines: pickEvidenceLines(text, commonHits, 4),
      summary: summarizeQuickFit(label, matched, missing)
    };
  }

  function analyzeQuickFit(jobId, pageText) {
    const text = normalizeText(pageText);
    if (!text) {
      return {
        label: "待识别",
        tone: "neutral",
        matched: [],
        missing: [],
        evidenceLines: [],
        summary: "当前页面还没有可分析的简历正文。"
      };
    }
    if (jobId === "py_dev_engineer_v1") {
      return analyzePythonQuickFit(text);
    }
    if (jobId === "caption_aesthetic_qc_v1") {
      return analyzeCaptionQcQuickFit(text);
    }
    if (jobId === "caption_ai_trainer_zhengzhou_v1") {
      return analyzeCaptionZhengzhouQuickFit(text);
    }
    if (jobId === "qa_test_engineer_v1") {
      return analyzeQaQuickFit(text);
    }
    return analyzeGenericQuickFit(text);
  }

  function decisionTone(decision) {
    if (decision === "recommend") {
      return "good";
    }
    if (decision === "review") {
      return "warn";
    }
    if (decision === "reject") {
      return "bad";
    }
    return "neutral";
  }

  function localizeJobName(jobId, fallbackName) {
    return JOB_NAME_MAP[jobId] || fallbackName || jobId || "";
  }

  function localizeDecision(decision) {
    return DECISION_LABELS[decision] || decision || DECISION_LABELS.pending;
  }

  function localizeStage(stage) {
    return PIPELINE_STAGE_LABELS[stage] || stage || PIPELINE_STAGE_LABELS.new;
  }

  function localizeSource(source) {
    return SOURCE_LABELS[source] || source || "";
  }

  function localizeError(errorCodeOrMessage) {
    return ERROR_LABELS[errorCodeOrMessage] || errorCodeOrMessage || "";
  }

  function localizeDimension(dimensionKey) {
    return DIMENSION_LABELS[dimensionKey] || dimensionKey || "";
  }

  return {
    DETAIL_ROOT_SELECTORS,
    HINT_SELECTORS,
    DETAIL_KEYWORDS,
    SIMILAR_SECTION_TITLES,
    JOB_OPTIONS_FALLBACK,
    JOB_NAME_MAP,
    DECISION_LABELS,
    PIPELINE_STAGE_LABELS,
    PIPELINE_STAGE_OPTIONS,
    SOURCE_LABELS,
    PREFS_STORAGE_KEY,
    DEFAULT_BACKEND_BASE_URL,
    ERROR_LABELS,
    DIMENSION_LABELS,
    normalizeText,
    normalizeCandidateNameText,
    shortText,
    hashText,
    buildCandidateKey,
    extractCandidateNameFragment,
    looksLikeCandidateName,
    normalizeBackendBaseUrl,
    extractYearsExperience,
    extractEducationLevel,
    analyzeQuickFit,
    decisionTone,
    localizeJobName,
    localizeDecision,
    localizeStage,
    localizeSource,
    localizeError,
    localizeDimension
  };
});
