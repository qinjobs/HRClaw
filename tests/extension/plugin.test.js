const test = require("node:test");
const assert = require("node:assert/strict");

globalThis.__BOSS_RESUME_SCORE_DISABLE_AUTO_INIT__ = true;

const shared = require("../../chrome_extensions/boss_resume_score/shared.js");
const contentScript = require("../../chrome_extensions/boss_resume_score/content-script.js");
const serviceWorker = require("../../chrome_extensions/boss_resume_score/service-worker.js");

function createDocument(map, bodyText, title) {
  const body = {
    innerText: bodyText || "",
    textContent: bodyText || "",
    getBoundingClientRect() {
      return { top: 0, bottom: 1200, width: 960, height: 1200 };
    }
  };
  const listMap = map.__queryAll || {};
  const defaultView = {
    innerHeight: 900,
    getComputedStyle(element) {
      return (element && element.__style) || {
        display: "block",
        visibility: "visible",
        opacity: "1"
      };
    }
  };
  return {
    title: title || "",
    body,
    defaultView,
    documentElement: {
      clientHeight: 900
    },
    querySelector(selector) {
      return map[selector] || null;
    },
    querySelectorAll(selector) {
      return listMap[selector] || [];
    }
  };
}

function createStorage() {
  const values = {};
  return {
    values,
    get(key, callback) {
      if (typeof key === "string") {
        callback({ [key]: values[key] });
        return;
      }
      callback(values);
    },
    set(payload, callback) {
      Object.assign(values, payload);
      callback();
    }
  };
}

function createRecommendCard(name, text, rect) {
  const nameNode = {
    tagName: "SPAN",
    innerText: name,
    textContent: name
  };
  return {
    innerText: text,
    textContent: text,
    getBoundingClientRect() {
      return rect || { top: 120, bottom: 280, width: 920, height: 160 };
    },
    querySelector(selector) {
      if (selector === ".name" || selector === ".name-label") {
        return nameNode;
      }
      return null;
    }
  };
}

test("content script extracts detail context from a BOSS resume frame", () => {
  const detailElement = {
    innerText: "张三\n测试工程师\n工作经历\n项目经历\n教育经历\n打招呼\n5年测试经验，本科，接口测试和回归测试。",
    textContent: "张三\n测试工程师\n工作经历\n项目经历\n教育经历\n打招呼\n5年测试经验，本科，接口测试和回归测试。"
  };
  const nameElement = {
    innerText: "张三 / QA Engineer",
    textContent: "张三 / QA Engineer"
  };
  const doc = createDocument(
    {
      ".resume-detail-wrap": detailElement,
      ".name-label": nameElement,
      __queryAll: {
        ".resume-detail-wrap": [detailElement]
      }
    },
    "",
    "BOSS Detail"
  );
  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/geek/job-recommend/a1b2c3.html" }, { frameId: 2 });

  assert.equal(context.isDetail, true);
  assert.equal(context.frameId, 2);
  assert.match(context.pageText, /工作经历/);
  assert.equal(context.candidateName, "张三");
  assert.equal(context.candidateHint, "张三");
  assert.equal(context.contextKey, shared.buildCandidateKey(context));
});

test("shared candidate name extractor accepts name plus active-status line and rejects script noise", () => {
  assert.equal(shared.extractCandidateNameFragment("孙奥杰 刚刚活跃"), "孙奥杰");
  assert.equal(shared.extractCandidateNameFragment("!function(){var e=document,t=e.createElement(\"script\")}"), "");
});

test("shared quick-fit analyzer returns an instant JD verdict for QA resumes", () => {
  const analysis = shared.analyzeQuickFit(
    "qa_test_engineer_v1",
    "孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n负责移动端 UI 自动化测试框架从0到1的设计与搭建，基于 Appium 构建可落地的自动化解决方案。\n具备接口自动化测试框架搭建能力，基于 Python + requests + pytest 实现接口自动化测试。\n熟练使用 ADB、Charles、MySQL。"
  );

  assert.equal(analysis.label, "基本符合");
  assert.ok(analysis.matched.some((entry) => entry.includes("本科")));
  assert.ok(analysis.matched.some((entry) => entry.includes("5 年")));
});

test("shared candidate key changes when only the later resume body changes", () => {
  const prefix = "推荐牛人\nBOSS直聘\n固定页头\n".repeat(40);
  const contextA = {
    pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
    pageTitle: "BOSS直聘",
    candidateName: "孙奥杰",
    candidateHint: "孙奥杰",
    pageText: prefix + "A 候选人擅长 Appium 与接口自动化测试。"
  };
  const contextB = {
    pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
    pageTitle: "BOSS直聘",
    candidateName: "孙奥杰",
    candidateHint: "孙奥杰",
    pageText: prefix + "B 候选人擅长 JMeter 与性能测试。"
  };

  assert.notEqual(shared.buildCandidateKey(contextA), shared.buildCandidateKey(contextB));
});

test("content script prefers the candidate name embedded in detail text over unrelated global name nodes", () => {
  const detailElement = {
    innerText: "朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n打招呼\n熟悉软件测试流程。",
    textContent: "朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n打招呼\n熟悉软件测试流程。"
  };
  const unrelatedNameElement = {
    innerText: "马聪博",
    textContent: "马聪博"
  };
  const doc = createDocument(
    {
      ".resume-detail-wrap": detailElement,
      ".name-label": unrelatedNameElement,
      __queryAll: {
        ".resume-detail-wrap": [detailElement]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/c-resume/?source=recommend" }, { frameId: 1 });

  assert.equal(context.isDetail, true);
  assert.equal(context.candidateName, "朱浩瀚");
  assert.equal(context.candidateHint, "朱浩瀚");
});

test("content script picks the strongest resume detail root instead of the first generic card", () => {
  const genericCard = {
    innerText: "马聪博\n工作经历\n教育经历\n测试工程师\n3年经验",
    textContent: "马聪博\n工作经历\n教育经历\n测试工程师\n3年经验",
    getBoundingClientRect() {
      return { top: 640, bottom: 860, width: 900, height: 220 };
    }
  };
  const resumeDetail = {
    innerText: "朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n打招呼\n熟悉软件测试流程。",
    textContent: "朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n打招呼\n熟悉软件测试流程。",
    getBoundingClientRect() {
      return { top: 48, bottom: 1180, width: 960, height: 1132 };
    }
  };
  const doc = createDocument(
    {
      ".resume-detail-wrap": resumeDetail,
      ".card-inner": genericCard,
      __queryAll: {
        ".resume-detail-wrap": [resumeDetail],
        ".card-inner": [genericCard]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/c-resume/?source=recommend" }, { frameId: 1 });

  assert.equal(context.isDetail, true);
  assert.equal(context.candidateName, "朱浩瀚");
});

test("content script prefers the currently visible resume detail when a stale candidate stays in the DOM", () => {
  const staleDetail = {
    innerText: "马聪博\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n" + "自动化测试经验\n".repeat(260),
    textContent: "马聪博\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n" + "自动化测试经验\n".repeat(260),
    getBoundingClientRect() {
      return { top: -2600, bottom: -320, width: 960, height: 2280 };
    }
  };
  const visibleDetail = {
    innerText: "孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉 Appium、Pytest、接口自动化测试。",
    textContent: "孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉 Appium、Pytest、接口自动化测试。",
    getBoundingClientRect() {
      return { top: 36, bottom: 1160, width: 960, height: 1124 };
    }
  };
  const doc = createDocument(
    {
      ".resume-detail-wrap": visibleDetail,
      __queryAll: {
        ".resume-detail-wrap": [staleDetail, visibleDetail]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/c-resume/?source=recommend" }, { frameId: 1 });

  assert.equal(context.isDetail, true);
  assert.equal(context.candidateName, "孙奥杰");
  assert.ok(Number(context.visibilityScore) > 0);
});

test("content script extracts the candidate name even when script noise appears before the resume header", () => {
  const detailElement = {
    innerText: "!function(){var e=document,t=e.createElement(\"script\")}\n孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉自动化测试。",
    textContent: "!function(){var e=document,t=e.createElement(\"script\")}\n孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉自动化测试。"
  };
  const doc = createDocument(
    {
      ".resume-detail-wrap": detailElement,
      __queryAll: {
        ".resume-detail-wrap": [detailElement]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/c-resume/?source=recommend" }, { frameId: 1 });

  assert.equal(context.isDetail, true);
  assert.equal(context.candidateName, "孙奥杰");
  assert.equal(context.candidateHint, "孙奥杰");
});

test("content script reports unsupported when no detail content is visible", () => {
  const doc = createDocument({}, "short text only", "BOSS");
  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/chat/recommend" }, { frameId: 0 });

  assert.equal(context.isDetail, false);
  assert.equal(context.reason, "candidate_detail_not_found");
});

test("content script ignores the similar-candidates section below the resume", () => {
  const detailElement = {
    innerText: "朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉软件测试流程。",
    textContent: "朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉软件测试流程。"
  };
  const similarHeading = {
    innerText: "其他相似经历的牛人",
    textContent: "其他相似经历的牛人",
    getBoundingClientRect() {
      return { top: 120, bottom: 156 };
    }
  };
  const doc = createDocument(
    {
      ".resume-detail-wrap": detailElement,
      __queryAll: {
        "h1,h2,h3,h4,strong,div,span,p": [similarHeading]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/c-resume/?source=recommend" }, { frameId: 1 });

  assert.equal(context.isDetail, false);
  assert.equal(context.reason, "candidate_detail_not_found");
});

test("content script does not treat the recommend list page as a scoreable detail view", () => {
  const cardA = createRecommendCard(
    "李悦童",
    "面议\n李悦童\n25岁 5年 本科 离职-随时到岗\n期望\n北京 测试工程师\n优势\n掌握测试理论基础。\n2023.04 2026.02\n万古恒信科技有线公司 软件测试工程师\n2018 2022\n东南大学成贤学院 计算机科学与技术 本科\n打招呼",
    { top: 180, bottom: 340, width: 920, height: 160 }
  );
  const cardB = createRecommendCard(
    "聂昕晨",
    "12-14K\n聂昕晨\n刚刚活跃\n25岁 5年 本科 离职-随时到岗\n最近关注\n北京 测试工程师\n优势\n具有 app/web/接口测试经验。\n2021.06 2025.03\n优贝在线（北京） 测试工程师\n2018 2022\n河北科技大学理工学院 计算机科学与技术 本科\n打招呼",
    { top: 360, bottom: 520, width: 920, height: 160 }
  );
  const summary = {
    innerText: "收藏\n不合适\n举报\n转发牛人\n打招呼\n经历概览\n优贝在线（北京）信息技术有限公司\n2021.06 - 2025.03\n测试工程师\n3年9个月\n河北科技大学理工学院\n2018 - 2022\n计算机科学与技术 • 本科",
    textContent: "收藏\n不合适\n举报\n转发牛人\n打招呼\n经历概览\n优贝在线（北京）信息技术有限公司\n2021.06 - 2025.03\n测试工程师\n3年9个月\n河北科技大学理工学院\n2018 - 2022\n计算机科学与技术 • 本科",
    getBoundingClientRect() {
      return { top: 120, bottom: 760, width: 420, height: 640 };
    }
  };
  const doc = createDocument(
    {
      ".resume-summary": summary,
      __queryAll: {
        ".candidate-card-wrap": [cardA, cardB]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/recommend/?jobId=123" }, { frameId: 1 });

  assert.equal(context.isDetail, false);
  assert.equal(context.reason, "candidate_detail_not_found");
});

test("content script matches the active recommend detail dialog to the correct candidate card", () => {
  const cardA = createRecommendCard(
    "许鼎基",
    "面议\n许鼎基\n刚刚活跃\n25岁 4年 本科 离职-随时到岗\n最近关注\n北京 测试工程师\n优势\n熟练掌握软件测试理论。\n2023.11 2026.01\n衣联 测试工程师\n2017 2021\n南通理工学院 软件工程 本科\n打招呼",
    { top: 180, bottom: 340, width: 920, height: 160 }
  );
  const cardB = createRecommendCard(
    "王小银",
    "14-15K\n王小银\n34岁 10年 本科 离职-随时到岗\n最近关注\n北京 测试工程师\n优势\n热爱软件测试行业。\n211院校\nPostman\nFiddler\nPython\n软件测试\n2024.11 至今\n三快在线 测试\n2021.07 2024.11\n字节跳动 软件测试工程师\n2018.11 2021.06\n腾跃智汇 测试工程师\n2022 2024\n西安电子科技大学 计算机科学与技术 本科\n打招呼",
    { top: 360, bottom: 520, width: 920, height: 160 }
  );
  const summary = {
    className: "resume-summary",
    innerText: "经历概览\n北京三快在线科技有限公司\n2024.11 - 至今\n测试\n1年4个月\n北京字节跳动科技有限公司\n2021.07 - 2024.11\n软件测试工程师\n3年4个月\n北京腾跃智汇网络科技有限公司\n2018.11 - 2021.06\n测试工程师\n2年7个月\n西安电子科技大学\n2022 - 2024\n计算机科学与技术 • 本科",
    textContent: "经历概览\n北京三快在线科技有限公司\n2024.11 - 至今\n测试\n1年4个月\n北京字节跳动科技有限公司\n2021.07 - 2024.11\n软件测试工程师\n3年4个月\n北京腾跃智汇网络科技有限公司\n2018.11 - 2021.06\n测试工程师\n2年7个月\n西安电子科技大学\n2022 - 2024\n计算机科学与技术 • 本科",
    getBoundingClientRect() {
      return { top: 120, bottom: 760, width: 420, height: 640 };
    }
  };
  const overlay = {
    className: "dialog-wrap active",
    innerText: "收藏\n不合适\n举报\n转发牛人\n打招呼\n经历概览",
    textContent: "收藏\n不合适\n举报\n转发牛人\n打招呼\n经历概览"
  };
  const doc = createDocument(
    {
      ".dialog-wrap.active": overlay,
      ".resume-summary": summary,
      __queryAll: {
        ".candidate-card-wrap": [cardA, cardB]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/recommend/?jobId=123" }, { frameId: 1 });

  assert.equal(context.isDetail, true);
  assert.equal(context.candidateName, "王小银");
  assert.match(context.pageText, /北京三快在线科技有限公司/);
  assert.match(context.pageText, /西安电子科技大学/);
});

test("content script prefers the freshly clicked recommend card while the old detail summary is still visible", () => {
  const cardA = createRecommendCard(
    "王小银",
    "14-15K\n王小银\n34岁 10年 本科 离职-随时到岗\n最近关注\n北京 测试工程师\n2024.11 至今\n三快在线 测试\n2021.07 2024.11\n字节跳动 软件测试工程师\n2022 2024\n西安电子科技大学 计算机科学与技术 本科\n打招呼",
    { top: 180, bottom: 340, width: 920, height: 160 }
  );
  const cardB = createRecommendCard(
    "吴国伟",
    "面议\n吴国伟\n28岁 6年 本科 离职-随时到岗\n最近关注\n北京 测试工程师\n2025.09 2026.01\n联想（北京） 测试工程师\n2023.06 2025.07\n普强信息技术（北京） 测试工程师\n2015 2019\n上海杉达学院 计算机科学与技术 本科\n打招呼",
    { top: 360, bottom: 520, width: 920, height: 160 }
  );
  const summary = {
    className: "resume-summary",
    innerText: "经历概览\n北京三快在线科技有限公司\n2024.11 - 至今\n测试\n1年4个月\n北京字节跳动科技有限公司\n2021.07 - 2024.11\n软件测试工程师\n3年4个月\n西安电子科技大学\n2022 - 2024\n计算机科学与技术 • 本科",
    textContent: "经历概览\n北京三快在线科技有限公司\n2024.11 - 至今\n测试\n1年4个月\n北京字节跳动科技有限公司\n2021.07 - 2024.11\n软件测试工程师\n3年4个月\n西安电子科技大学\n2022 - 2024\n计算机科学与技术 • 本科",
    getBoundingClientRect() {
      return { top: 120, bottom: 760, width: 420, height: 640 };
    }
  };
  const overlay = {
    className: "dialog-wrap active",
    innerText: "收藏\n不合适\n举报\n转发牛人\n打招呼\n经历概览",
    textContent: "收藏\n不合适\n举报\n转发牛人\n打招呼\n经历概览"
  };
  globalThis.__BOSS_RESUME_SCORE_SELECTION_EPOCH__ = 7;
  globalThis.__BOSS_RESUME_SCORE_PENDING_SELECTION__ = {
    geekId: "target-2",
    candidateName: "吴国伟",
    observedAt: Date.now(),
    selectionEpoch: 7
  };
  cardB.getAttribute = function (name) {
    return name === "data-geekid" ? "target-2" : "";
  };
  cardA.getAttribute = function () {
    return "";
  };
  const doc = createDocument(
    {
      ".dialog-wrap.active": overlay,
      ".resume-summary": summary,
      __queryAll: {
        ".candidate-card-wrap": [cardA, cardB]
      }
    },
    "",
    "BOSS Detail"
  );

  const context = contentScript.extractPageContext(doc, { href: "https://www.zhipin.com/web/frame/recommend/?jobId=123" }, { frameId: 1 });

  assert.equal(context.isDetail, true);
  assert.equal(context.candidateName, "吴国伟");
  assert.doesNotMatch(context.pageText, /北京三快在线科技有限公司/);
  assert.match(context.pageText, /联想（北京）/);
  delete globalThis.__BOSS_RESUME_SCORE_PENDING_SELECTION__;
  delete globalThis.__BOSS_RESUME_SCORE_SELECTION_EPOCH__;
});

test("content script does not render quick-fit badge inside the recommend list page", () => {
  const ids = {};
  function createMountRoot(className, text, rect) {
    return {
      className,
      innerText: text,
      textContent: text,
      getBoundingClientRect() {
        return rect;
      },
      prepend(node) {
        node.parentElement = this;
        if (node.id) {
          ids[node.id] = node;
        }
      }
    };
  }

  const detailRoot = createMountRoot(
    "card-inner common-wrap css-type-1",
    "聂昕晨\n工作经历\n项目经历\n教育经历\n5年测试经验",
    { top: 180, bottom: 360, width: 920, height: 180 }
  );
  const summaryRoot = createMountRoot(
    "resume-right-side",
    "经历概览\n优贝在线（北京）信息技术有限公司\n河北科技大学理工学院",
    { top: 120, bottom: 760, width: 420, height: 640 }
  );
  const doc = {
    title: "BOSS直聘",
    location: { href: "https://www.zhipin.com/web/frame/recommend/?jobId=123" },
    body: {
      innerText: "聂昕晨\n工作经历\n项目经历\n教育经历",
      textContent: "聂昕晨\n工作经历\n项目经历\n教育经历",
      getBoundingClientRect() {
        return { top: 0, bottom: 1200, width: 960, height: 1200 };
      }
    },
    documentElement: { clientHeight: 900 },
    defaultView: {
      innerHeight: 900,
      getComputedStyle() {
        return { display: "block", visibility: "visible", opacity: "1" };
      }
    },
    querySelector(selector) {
      if (selector === ".resume-right-side") {
        return summaryRoot;
      }
      if (selector === ".card-inner") {
        return detailRoot;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".card-inner") {
        return [detailRoot];
      }
      if (selector === "h1,h2,h3,h4,strong,div,span,p") {
        return [];
      }
      return [];
    },
    createElement(tag) {
      return {
        tagName: String(tag || "").toUpperCase(),
        style: { cssText: "" },
        innerHTML: "",
        id: "",
        parentElement: null,
        remove() {
          if (this.id) {
            delete ids[this.id];
          }
          this.parentElement = null;
        }
      };
    },
    getElementById(id) {
      return ids[id] || null;
    }
  };

  const result = contentScript.renderQuickFitBadge(doc, {
    label: "基本符合",
    tone: "good",
    summary: "已命中核心 JD 条件。",
    matched: ["本科及以上学历", "5 年测试经验"],
    evidenceLines: ["优贝在线（北京）信息技术有限公司"]
  });

  assert.equal(result.ok, false);
  assert.equal(result.reason, "candidate_detail_not_found");
  assert.equal(ids["boss-resume-quick-fit-badge"], undefined);
});

test("content script hides the page-level quick-fit verdict label on detail pages", () => {
  const ids = {};
  const detailRoot = {
    className: "resume-detail-wrap",
    innerText: "杜鹏博\n工作经历\n项目经历\n教育经历\n6年测试经验",
    textContent: "杜鹏博\n工作经历\n项目经历\n教育经历\n6年测试经验",
    getBoundingClientRect() {
      return { top: 48, bottom: 1180, width: 960, height: 1132 };
    },
    prepend(node) {
      node.parentElement = this;
      if (node.id) {
        ids[node.id] = node;
      }
    }
  };
  const doc = {
    title: "BOSS直聘",
    location: { href: "https://www.zhipin.com/web/frame/c-resume/?source=recommend" },
    body: {
      innerText: "杜鹏博\n工作经历\n项目经历\n教育经历\n6年测试经验",
      textContent: "杜鹏博\n工作经历\n项目经历\n教育经历\n6年测试经验",
      getBoundingClientRect() {
        return { top: 0, bottom: 1200, width: 960, height: 1200 };
      }
    },
    documentElement: { clientHeight: 900 },
    defaultView: {
      innerHeight: 900,
      getComputedStyle() {
        return { display: "block", visibility: "visible", opacity: "1" };
      }
    },
    querySelector(selector) {
      if (selector === ".resume-detail-wrap") {
        return detailRoot;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".resume-detail-wrap") {
        return [detailRoot];
      }
      if (selector === "h1,h2,h3,h4,strong,div,span,p") {
        return [];
      }
      return [];
    },
    createElement(tag) {
      return {
        tagName: String(tag || "").toUpperCase(),
        style: { cssText: "" },
        innerHTML: "",
        id: "",
        parentElement: null,
        remove() {
          if (this.id) {
            delete ids[this.id];
          }
          this.parentElement = null;
        }
      };
    },
    getElementById(id) {
      return ids[id] || null;
    }
  };

  const result = contentScript.renderQuickFitBadge(doc, {
    label: "明显不符",
    tone: "bad",
    summary: "当前简历未命中岗位核心要求。",
    matched: [],
    evidenceLines: ["缺少自动化测试相关经历。"]
  });

  assert.equal(result.ok, true);
  assert.equal(ids["boss-resume-quick-fit-badge"].parentElement, detailRoot);
  assert.doesNotMatch(ids["boss-resume-quick-fit-badge"].innerHTML, /明显不符/);
  assert.match(ids["boss-resume-quick-fit-badge"].innerHTML, /当前简历未命中岗位核心要求/);
});

test("service worker score service uses session cache and force bypass", async () => {
  const storage = serviceWorker.createStorageAdapter(createStorage());
  let fetchCount = 0;
  const scoreService = serviceWorker.createScoreService({
    storage,
    fetchImpl: async () => {
      fetchCount += 1;
      return {
        ok: true,
        async json() {
          return {
            score: 86.4,
            decision: "recommend",
            dimension_scores: { tools_coverage: 18.2 },
            hard_filter_fail_reasons: [],
            review_reasons: [],
            extracted_fields: {},
            fallback_used: false,
            model_usage: { total_tokens: 100 },
            scored_at: "2026-03-18T04:00:00Z"
          };
        }
      };
    },
    backendBaseUrl: "http://127.0.0.1:8080"
  });
  const context = {
    pageUrl: "https://www.zhipin.com/web/geek/job-recommend/cache001.html",
    pageTitle: "BOSS Detail",
    pageText: "5年测试经验，本科，接口测试和回归测试。",
    candidateName: "张三",
    candidateHint: "张三 / QA"
  };

  const first = await scoreService.scoreContext({ jobId: "qa_test_engineer_v1", context, force: false });
  const second = await scoreService.scoreContext({ jobId: "qa_test_engineer_v1", context, force: false });
  const third = await scoreService.scoreContext({ jobId: "qa_test_engineer_v1", context, force: true });

  assert.equal(first.cacheHit, false);
  assert.equal(second.cacheHit, true);
  assert.equal(third.cacheHit, false);
  assert.equal(fetchCount, 2);
});

test("service worker cache key changes with candidate context", async () => {
  const storage = serviceWorker.createStorageAdapter(createStorage());
  let fetchCount = 0;
  const scoreService = serviceWorker.createScoreService({
    storage,
    fetchImpl: async () => {
      fetchCount += 1;
      return {
        ok: true,
        async json() {
          return {
            score: 70,
            decision: "review",
            dimension_scores: {},
            hard_filter_fail_reasons: [],
            review_reasons: [],
            extracted_fields: {},
            fallback_used: true,
            model_usage: { total_tokens: 0 },
            scored_at: "2026-03-18T04:01:00Z"
          };
        }
      };
    }
  });
  const contextA = {
    pageUrl: "https://www.zhipin.com/web/geek/job-recommend/a10001.html",
    pageTitle: "BOSS Detail",
    pageText: "Candidate A",
    candidateName: "A",
    candidateHint: "A"
  };
  const contextB = {
    pageUrl: "https://www.zhipin.com/web/geek/job-recommend/b20002.html",
    pageTitle: "BOSS Detail",
    pageText: "Candidate B",
    candidateName: "B",
    candidateHint: "B"
  };

  const keyA = scoreService.buildCacheKey("qa_test_engineer_v1", contextA);
  const keyB = scoreService.buildCacheKey("qa_test_engineer_v1", contextB);
  await scoreService.scoreContext({ jobId: "qa_test_engineer_v1", context: contextA, force: false });
  await scoreService.scoreContext({ jobId: "qa_test_engineer_v1", context: contextB, force: false });

  assert.notEqual(keyA, keyB);
  assert.equal(fetchCount, 2);
});

test("service worker candidate service upserts and caches candidate records", async () => {
  const sessionStorage = createStorage();
  const localStorage = createStorage();
  localStorage.values[shared.PREFS_STORAGE_KEY] = {
    jobId: "qa_test_engineer_v1",
    backendBaseUrl: "http://192.168.1.88:8080"
  };
  const calls = [];
  const candidateService = serviceWorker.createCandidateService({
    storage: serviceWorker.createStorageAdapter(sessionStorage),
    prefsStorage: serviceWorker.createStorageAdapter(localStorage),
    fetchImpl: async (url, options) => {
      calls.push({
        url,
        body: JSON.parse(options.body)
      });
      return {
        ok: true,
        async json() {
          return {
            candidate_id: "cand-001",
            task_id: "task-001",
            created_new: true,
            pipeline_state: {
              current_stage: "new",
              manual_stage_locked: false
            }
          };
        }
      };
    }
  });
  const context = {
    pageUrl: "https://www.zhipin.com/web/frame/recommend/?jobId=123",
    pageTitle: "BOSS Detail",
    pageText: "吴国伟\n28岁 6年 本科\n工作经历\n联想（北京） 测试工程师",
    candidateName: "吴国伟",
    candidateHint: "吴国伟",
    geekId: "geek-001",
    contextKey: "ctx-001"
  };

  const first = await candidateService.ensureCandidateForContext({ jobId: "qa_test_engineer_v1", context, force: false });
  const second = await candidateService.ensureCandidateForContext({ jobId: "qa_test_engineer_v1", context, force: false });

  assert.equal(first.cacheHit, false);
  assert.equal(second.cacheHit, true);
  assert.equal(first.candidate_id, "cand-001");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://192.168.1.88:8080/api/extension/candidates/upsert");
  assert.equal(calls[0].body.source_candidate_key, "geek-001");
});

test("service worker score service reads backend url from local prefs", async () => {
  const storage = serviceWorker.createStorageAdapter(createStorage());
  const localStorage = createStorage();
  localStorage.values[shared.PREFS_STORAGE_KEY] = {
    backendBaseUrl: "http://192.168.1.88:8080"
  };
  const urls = [];
  const scoreService = serviceWorker.createScoreService({
    storage,
    prefsStorage: serviceWorker.createStorageAdapter(localStorage),
    fetchImpl: async (url) => {
      urls.push(url);
      return {
        ok: true,
        async json() {
          return {
            score: 81.2,
            decision: "review",
            dimension_scores: {},
            hard_filter_fail_reasons: [],
            review_reasons: [],
            extracted_fields: {},
            fallback_used: false,
            model_usage: { total_tokens: 1 },
            scored_at: "2026-03-20T02:00:00Z"
          };
        }
      };
    }
  });

  await scoreService.scoreContext({
    jobId: "qa_test_engineer_v1",
    context: {
      pageUrl: "https://www.zhipin.com/web/geek/job-recommend/cache001.html",
      pageTitle: "BOSS Detail",
      pageText: "5年测试经验，本科，接口测试和回归测试。",
      candidateName: "张三",
      candidateHint: "张三"
    },
    force: true
  });

  assert.equal(urls[0], "http://192.168.1.88:8080/api/extension/score");
});

test("service worker score service lists scoring targets for custom scorecards", async () => {
  const scoreService = serviceWorker.createScoreService({
    fetchImpl: async (url) => {
      assert.equal(url, "http://127.0.0.1:8080/api/scoring-targets");
      return {
        ok: true,
        async json() {
          return {
            items: [
              { id: "qa_test_engineer_v1", name: "QA Test Engineer", kind: "builtin_phase1" },
              { id: "custom-python-bj", name: "Python开发-北京", kind: "custom_phase2" }
            ]
          };
        }
      };
    },
    backendBaseUrl: "http://127.0.0.1:8080"
  });

  const items = await scoreService.listJobs();
  assert.equal(items.length, 2);
  assert.equal(items[1].id, "custom-python-bj");
  assert.equal(items[1].name, "Python开发-北京");
});

test("service worker score service uses candidate-specific score endpoint when candidate id exists", async () => {
  const storage = serviceWorker.createStorageAdapter(createStorage());
  const urls = [];
  const scoreService = serviceWorker.createScoreService({
    storage,
    fetchImpl: async (url) => {
      urls.push(url);
      return {
        ok: true,
        async json() {
          return {
            candidate_id: "cand-001",
            score: 86.4,
            decision: "recommend",
            hard_filter_pass: true,
            dimension_scores: { tools_coverage: 18.2 },
            hard_filter_fail_reasons: [],
            review_reasons: [],
            extracted_fields: {},
            fallback_used: false,
            model_usage: { total_tokens: 100 },
            scored_at: "2026-03-18T04:00:00Z",
            pipeline_state: { current_stage: "scored" }
          };
        }
      };
    },
    backendBaseUrl: "http://127.0.0.1:8080"
  });
  const context = {
    pageUrl: "https://www.zhipin.com/web/geek/job-recommend/cache001.html",
    pageTitle: "BOSS Detail",
    pageText: "5年测试经验，本科，接口测试和回归测试。",
    candidateName: "张三",
    candidateHint: "张三 / QA"
  };

  const result = await scoreService.scoreContext({
    jobId: "qa_test_engineer_v1",
    context,
    candidateId: "cand-001",
    force: true
  });

  assert.equal(result.candidate_id, "cand-001");
  assert.match(urls[0], /\/api\/extension\/candidates\/cand-001\/score$/);
});

test("service worker prefers the context with a valid candidate name", () => {
  const best = serviceWorker.pickBestContext([
    {
      frameId: 0,
      pageUrl: "https://www.zhipin.com/web/frame/recommend/?jobId=123",
      pageText: "!function(){var e=document,t=e.createElement(\"script\")}\n工作经历\n项目经历\n教育经历\n".repeat(40),
      candidateName: "",
      candidateHint: ""
    },
    {
      frameId: 1,
      pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
      pageText: "孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历",
      candidateName: "孙奥杰",
      candidateHint: "孙奥杰"
    }
  ]);

  assert.equal(best.frameId, 1);
  assert.equal(best.candidateName, "孙奥杰");
});

test("service worker prefers the visible current context over a longer stale one", () => {
  const best = serviceWorker.pickBestContext([
    {
      frameId: 0,
      pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
      pageText: "马聪博 刚刚活跃\n26岁 6年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n" + "自动化测试经验\n".repeat(260),
      candidateName: "马聪博",
      candidateHint: "马聪博",
      visibilityScore: -3200
    },
    {
      frameId: 1,
      pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
      pageText: "孙奥杰 刚刚活跃\n26岁 5年 本科 在职-月内到岗\n工作经历\n项目经历\n教育经历\n熟悉 Appium、Pytest、接口自动化测试。",
      candidateName: "孙奥杰",
      candidateHint: "孙奥杰",
      visibilityScore: 5700
    }
  ]);

  assert.equal(best.frameId, 1);
  assert.equal(best.candidateName, "孙奥杰");
});

test("service worker keeps the latest live context per tab and expires old entries", () => {
  const liveContextsByTab = {};
  serviceWorker.rememberLiveContext(liveContextsByTab, 88, 1, {
    isDetail: true,
    frameId: 1,
    pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
    pageText: "孙奥杰 刚刚活跃\n工作经历\n项目经历\n教育经历",
    candidateName: "孙奥杰",
    candidateHint: "孙奥杰",
    visibilityScore: 4200
  }, 1000);
  serviceWorker.rememberLiveContext(liveContextsByTab, 88, 2, {
    isDetail: true,
    frameId: 2,
    pageUrl: "https://www.zhipin.com/web/frame/c-resume/?source=recommend",
    pageText: "马聪博 刚刚活跃\n工作经历\n项目经历\n教育经历",
    candidateName: "马聪博",
    candidateHint: "马聪博",
    visibilityScore: -3000
  }, 1200);

  const activeNow = serviceWorker.collectLiveContexts(liveContextsByTab, 88, 2000);
  assert.equal(activeNow.length, 2);
  assert.equal(serviceWorker.pickBestContext(activeNow).candidateName, "孙奥杰");

  const expired = serviceWorker.collectLiveContexts(liveContextsByTab, 88, 20000);
  assert.equal(expired.length, 0);
});

test("service worker ignores an older live context epoch for the same frame", () => {
  const liveContextsByTab = {};
  serviceWorker.rememberLiveContext(liveContextsByTab, 66, 1, {
    isDetail: true,
    frameId: 1,
    pageUrl: "https://www.zhipin.com/web/frame/recommend/?jobId=123",
    pageText: "吴国伟\n联想（北京）\n上海杉达学院",
    candidateName: "吴国伟",
    candidateHint: "吴国伟",
    selectionEpoch: 9,
    observedAt: 9000
  }, 9000);
  serviceWorker.rememberLiveContext(liveContextsByTab, 66, 1, {
    isDetail: true,
    frameId: 1,
    pageUrl: "https://www.zhipin.com/web/frame/recommend/?jobId=123",
    pageText: "王小银\n三快在线\n西安电子科技大学",
    candidateName: "王小银",
    candidateHint: "王小银",
    selectionEpoch: 8,
    observedAt: 9500
  }, 9500);

  const active = serviceWorker.collectLiveContexts(liveContextsByTab, 66, 9600);
  assert.equal(active.length, 1);
  assert.equal(active[0].candidateName, "吴国伟");
});
