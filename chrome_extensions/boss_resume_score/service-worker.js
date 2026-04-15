try {
  if (typeof importScripts === "function") {
    importScripts("shared.js");
  }
} catch (error) {
  // Ignore import errors in non-extension test environments.
}

(function (root, factory) {
  const api = factory(root, root.BossResumeScoreShared || (typeof require === "function" ? require("./shared.js") : null));
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BossResumeScoreServiceWorker = api;
  if (!root.__BOSS_RESUME_SCORE_DISABLE_AUTO_INIT__ && root.chrome && root.chrome.runtime) {
    api.register(root.chrome);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (root, shared) {
  const BACKEND_BASE_URL = shared.DEFAULT_BACKEND_BASE_URL || "http://127.0.0.1:8080";
  const LIVE_CONTEXT_TTL_MS = 15000;

  function callbackToPromise(register) {
    return new Promise(function (resolve, reject) {
      try {
        register(function (result) {
          const runtime = root.chrome && root.chrome.runtime;
          if (runtime && runtime.lastError) {
            reject(new Error(runtime.lastError.message));
            return;
          }
          resolve(result);
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  function createStorageAdapter(storageArea) {
    return {
      async get(key) {
        if (!storageArea || typeof storageArea.get !== "function") {
          return undefined;
        }
        const payload = await callbackToPromise(function (done) {
          storageArea.get(key, done);
        });
        if (typeof key === "string") {
          return payload ? payload[key] : undefined;
        }
        return payload;
      },
      async set(value) {
        if (!storageArea || typeof storageArea.set !== "function") {
          return;
        }
        await callbackToPromise(function (done) {
          storageArea.set(value, done);
        });
      }
    };
  }

  function buildCacheKey(jobId, context) {
    return "boss_resume_score:" + String(jobId || "") + ":" + shared.buildCandidateKey(context || {});
  }

  function scoreContextIdentity(context) {
    const pageUrl = String((context && context.pageUrl) || "");
    let score = 0;
    if (shared.looksLikeCandidateName(context && context.candidateName)) {
      score += 100000;
    }
    if (shared.looksLikeCandidateName(context && context.candidateHint)) {
      score += 10000;
    }
    if (pageUrl.includes("/web/frame/c-resume/")) {
      score += 4000;
    }
    if (pageUrl.includes("/web/frame/recommend/")) {
      score += 2000;
    }
    score += Math.min(String((context && context.pageText) || "").length, 8000);
    score += Number((context && context.visibilityScore) || 0);
    return score;
  }

  function pickBestContext(contexts) {
    return (contexts || [])
      .slice()
      .sort(function (left, right) {
        return scoreContextIdentity(right) - scoreContextIdentity(left);
      })[0] || null;
  }

  function rememberLiveContext(store, tabId, frameId, context, nowMs) {
    if (!store || tabId === undefined || tabId === null) {
      return;
    }
    const tabKey = String(tabId);
    if (!store[tabKey]) {
      store[tabKey] = {};
    }
    const frameKey = String(frameId || 0);
    if (!context || !context.isDetail || !context.pageText) {
      delete store[tabKey][frameKey];
      if (!Object.keys(store[tabKey]).length) {
        delete store[tabKey];
      }
      return;
    }
    const nextObservedAt = Number((context && context.observedAt) || nowMs || Date.now());
    const nextEpoch = Number((context && context.selectionEpoch) || 0);
    const previous = store[tabKey][frameKey];
    if (previous) {
      const previousEpoch = Number(previous.selectionEpoch || 0);
      const previousObservedAt = Number(previous.observedAt || 0);
      if (previousEpoch > nextEpoch) {
        return;
      }
      if (previousEpoch === nextEpoch && previousObservedAt > nextObservedAt) {
        return;
      }
    }
    store[tabKey][frameKey] = Object.assign({}, context, {
      frameId: frameId || 0,
      observedAt: nextObservedAt,
      selectionEpoch: nextEpoch
    });
  }

  function collectLiveContexts(store, tabId, nowMs) {
    if (!store || tabId === undefined || tabId === null) {
      return [];
    }
    const tabKey = String(tabId);
    const tabStore = store[tabKey];
    if (!tabStore) {
      return [];
    }
    const now = Number(nowMs || Date.now());
    const contexts = [];
    Object.keys(tabStore).forEach(function (frameKey) {
      const entry = tabStore[frameKey];
      if (!entry) {
        return;
      }
      if (now - Number(entry.observedAt || 0) > LIVE_CONTEXT_TTL_MS) {
        delete tabStore[frameKey];
        return;
      }
      contexts.push(entry);
    });
    if (!Object.keys(tabStore).length) {
      delete store[tabKey];
    }
    return contexts;
  }

  function createPageContextConfig() {
    return {
      detailRootSelectors: shared.DETAIL_ROOT_SELECTORS || [],
      hintSelectors: shared.HINT_SELECTORS || [],
      detailKeywords: shared.DETAIL_KEYWORDS || []
    };
  }

  function extractPageContextInPage(config) {
    const PENDING_SELECTION_TTL_MS = 2600;

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

    function firstMatch(selectors, scopeNode) {
      const scope = scopeNode && typeof scopeNode.querySelector === "function" ? scopeNode : document;
      if (!scope || typeof scope.querySelector !== "function") {
        return null;
      }
      for (const selector of selectors || []) {
        const element = scope.querySelector(selector);
        if (element) {
          return element;
        }
      }
      return null;
    }

    function collectText(element) {
      if (!element) {
        return "";
      }
      return normalizeText(element.innerText || element.textContent || "");
    }

    function queryAll(selector) {
      if (!document || typeof document.querySelectorAll !== "function") {
        return [];
      }
      try {
        return Array.from(document.querySelectorAll(selector) || []);
      } catch (error) {
        return [];
      }
    }

    function normalizeCandidateName(value) {
      return normalizeText(value).replace(/[♂♀]/g, "").trim();
    }

    function findLikelyCandidateName(value) {
      const normalized = normalizeCandidateName(value);
      const lowered = normalized.toLowerCase();
      const noiseTokens = ["!function", "createelement(\"script\")", "createelement('script')", "nomodule", "document", "window.", "webpack", "vite", "<script", "function(", "=>"];
      const blockedTokens = new Set(["打招呼", "工作经历", "项目经历", "教育经历", "经历概览", "最近关注", "期望职位", "测试工程师", "测试开发", "刚刚活跃", "今日活跃", "在线", "活跃", "热搜", "本科", "硕士", "博士", "大专", "专科", "院校", "职位", "经历", "公司", "面议"]);
      if (!normalized || normalized.length > 80 || noiseTokens.some(function (token) { return lowered.includes(token); })) {
        return "";
      }
      const leadingMatch = normalized.match(/^([\u4e00-\u9fa5·*]{2,8})(?:\s|$|[\/|｜-])/);
      if (leadingMatch && !blockedTokens.has(leadingMatch[1])) {
        return leadingMatch[1];
      }
      const matches = normalized.match(/[\u4e00-\u9fa5·*]{2,8}/g) || [];
      for (const entry of matches) {
        if (!blockedTokens.has(entry)) {
          return entry;
        }
      }
      return "";
    }

    function candidateNameFromText(pageText) {
      const lines = normalizeText(pageText)
        .split("\n")
        .map(function (line) { return normalizeCandidateName(line); })
        .filter(Boolean);
      const profileLinePattern = /(岁|年|本科|硕士|博士|大专|专科|到岗|离职|在职)/;

      for (let index = 0; index < Math.min(lines.length, 18); index += 1) {
        const current = lines[index];
        const next = lines[index + 1] || "";
        const maybeName = findLikelyCandidateName(current);
        if (maybeName && (profileLinePattern.test(next) || /活跃|在线/.test(current))) {
          return maybeName;
        }
      }

      for (let index = 0; index < Math.min(lines.length, 8); index += 1) {
        const maybeName = findLikelyCandidateName(lines[index]);
        if (maybeName) {
          return maybeName;
        }
      }

      return "";
    }

    function extractCandidateName(pageText, detailRoot) {
      const textName = candidateNameFromText(pageText);
      if (textName) {
        return textName;
      }

      const scopedHintElement = detailRoot && typeof detailRoot.querySelector === "function"
        ? firstMatch(config && config.hintSelectors, detailRoot)
        : null;
      const scopedHintText = findLikelyCandidateName(collectText(scopedHintElement));
      if (scopedHintText) {
        return scopedHintText;
      }

      const safeGlobalSelectors = [".name-label", ".candidate-head .name", ".geek-name", ".resume-top-wrap .name"];
      const hintElement = firstMatch(safeGlobalSelectors);
      return findLikelyCandidateName(collectText(hintElement));
    }

    function isDetailText(text) {
      if (!text) {
        return false;
      }
      const keywordHits = (config && config.detailKeywords ? config.detailKeywords : []).filter(function (entry) {
        return text.includes(entry);
      }).length;
      return keywordHits >= 3 || text.length >= 160 || (text.length >= 60 && keywordHits >= 2);
    }

    function collectDetailRoots() {
      const seen = new Set();
      const roots = [];
      for (const selector of (config && config.detailRootSelectors) || []) {
        for (const element of queryAll(selector)) {
          if (!element || seen.has(element)) {
            continue;
          }
          seen.add(element);
          roots.push(element);
        }
      }
      return roots;
    }

    function visibilityScore(element) {
      if (!element) {
        return 0;
      }
      if (typeof window !== "undefined" && window && typeof window.getComputedStyle === "function") {
        try {
          const style = window.getComputedStyle(element);
          if (style && (style.display === "none" || style.visibility === "hidden" || style.opacity === "0")) {
            return -9000;
          }
        } catch (error) {
          // Ignore transient style lookup failures.
        }
      }
      if (typeof element.getBoundingClientRect !== "function") {
        return 0;
      }
      const rect = element.getBoundingClientRect();
      if (!rect || !Number.isFinite(rect.top)) {
        return 0;
      }
      const width = Number(rect.width || 0);
      const height = Number(rect.height || 0);
      if (width <= 1 || height <= 1) {
        return -7000;
      }
      const viewportHeight = Number(
        (typeof window !== "undefined" && window && window.innerHeight)
        || (document && document.documentElement && document.documentElement.clientHeight)
        || 0
      );
      if (!viewportHeight) {
        return 0;
      }
      const top = Number(rect.top);
      const bottom = Number(rect.bottom !== undefined ? rect.bottom : (rect.top + height));
      if (bottom <= 0 || top >= viewportHeight) {
        return -3200;
      }
      let score = 3600;
      const visibleTop = Math.max(0, top);
      const visibleBottom = Math.min(viewportHeight, bottom);
      const visibleHeight = Math.max(0, visibleBottom - visibleTop);
      if (top >= -80 && top <= viewportHeight * 0.42) {
        score += 900;
      }
      if (visibleHeight >= Math.min(height, viewportHeight * 0.45)) {
        score += 1200;
      }
      return score;
    }

    function scoreDetailRoot(element) {
      const text = collectText(element);
      if (!isDetailText(text)) {
        return Number.NEGATIVE_INFINITY;
      }
      const keywordHits = ((config && config.detailKeywords) || []).filter(function (entry) {
        return text.includes(entry);
      }).length;
      let score = keywordHits * 100 + Math.min(text.length, 4000);
      score += visibilityScore(element);
      if (text.includes("工作经历")) {
        score += 280;
      }
      if (text.includes("教育经历")) {
        score += 220;
      }
      if (text.includes("期望职位")) {
        score += 120;
      }
      if (/^[\u4e00-\u9fa5·*]{2,8}\n.*(岁|年|本科|硕士|博士|大专|专科|到岗|离职|在职)/.test(text)) {
        score += 260;
      }
      if (text.includes("其他相似经历的牛人")) {
        score -= 480;
      }
      return score;
    }

    function findSimilarSectionAnchor() {
      const titles = (shared && shared.SIMILAR_SECTION_TITLES) || [];
      const candidates = queryAll("h1,h2,h3,h4,strong,div,span,p");
      for (const title of titles) {
        let bestMatch = null;
        let bestLength = Number.POSITIVE_INFINITY;
        for (const element of candidates) {
          const text = collectText(element);
          if (!text || text.indexOf(title) === -1) {
            continue;
          }
          if (text === title) {
            return element;
          }
          if (text.length < bestLength) {
            bestMatch = element;
            bestLength = text.length;
          }
        }
        if (bestMatch) {
          return bestMatch;
        }
      }
      return null;
    }

    function isSimilarSectionActive() {
      const anchor = findSimilarSectionAnchor();
      if (!anchor || typeof anchor.getBoundingClientRect !== "function") {
        return false;
      }
      const rect = anchor.getBoundingClientRect();
      const viewportHeight = Number(
        (typeof window !== "undefined" && window && window.innerHeight)
        || (document && document.documentElement && document.documentElement.clientHeight)
        || 0
      );
      if (!Number.isFinite(rect.top)) {
        return false;
      }
      if (!viewportHeight) {
        return rect.top <= 320;
      }
      return rect.top <= viewportHeight * 0.55;
    }

    function deriveCandidateHint(pageText, detailRoot, candidateName) {
      if (candidateName) {
        return shortText(candidateName, 80);
      }

      const scopedHintElement = detailRoot && typeof detailRoot.querySelector === "function"
        ? firstMatch(config && config.hintSelectors, detailRoot)
        : null;
      const scopedHintText = findLikelyCandidateName(collectText(scopedHintElement));
      if (scopedHintText) {
        return shortText(scopedHintText, 80);
      }

      const hintElement = firstMatch(config && config.hintSelectors);
      const hintText = findLikelyCandidateName(collectText(hintElement));
      if (hintText) {
        return shortText(hintText, 80);
      }

      const lines = normalizeText(pageText).split("\n");
      const firstLine = lines.find(function (line) {
        return line && line.length <= 40;
      }) || lines[0] || "";
      const firstLineName = findLikelyCandidateName(firstLine);
      return firstLineName ? shortText(firstLineName, 80) : "";
    }

    function tokenizeSelectionText(text) {
      return normalizeText(text)
        .split("\n")
        .map(function (line) { return normalizeText(line); })
        .filter(function (line) {
          return line
            && line.length >= 4
            && line.length <= 40
            && !/^(收藏|不合适|举报|转发牛人|打招呼|经历概览|最近关注|期望|测试工程师|\d+岁|\d+年|本科|硕士|博士|大专|专科)$/.test(line)
            && !/^\d{4}([.-]\d{2})?/.test(line);
        })
        .slice(0, 12);
    }

    function nowMs() {
      return Date.now();
    }

    function currentSelectionEpoch() {
      return Number((typeof window !== "undefined" && window && window.__BOSS_RESUME_SCORE_SELECTION_EPOCH__) || 0);
    }

    function getPendingSelection() {
      const pending = typeof window !== "undefined" && window ? window.__BOSS_RESUME_SCORE_PENDING_SELECTION__ : null;
      if (!pending) {
        return null;
      }
      if (nowMs() - Number(pending.observedAt || 0) > PENDING_SELECTION_TTL_MS) {
        if (typeof window !== "undefined" && window) {
          window.__BOSS_RESUME_SCORE_PENDING_SELECTION__ = null;
        }
        return null;
      }
      return pending;
    }

    function extractCardSnapshot(card) {
      if (!card) {
        return null;
      }
      const nameNode = firstMatch([".name", ".name-label", "img[alt]"], card);
      let candidateName = "";
      if (nameNode && nameNode.tagName === "IMG" && typeof nameNode.getAttribute === "function") {
        candidateName = findLikelyCandidateName(nameNode.getAttribute("alt") || "");
      } else {
        candidateName = findLikelyCandidateName(collectText(nameNode));
      }
      return {
        geekId: typeof card.getAttribute === "function" ? (card.getAttribute("data-geekid") || card.getAttribute("data-geek") || "") : "",
        candidateName: candidateName,
        cardText: collectText(card),
        observedAt: nowMs(),
        selectionEpoch: currentSelectionEpoch()
      };
    }

    function hasRecommendDetailOverlay() {
      const dialogRoot = firstMatch([
        ".dialog-wrap.active",
        ".boss-popup__wrapper.recommendV2"
      ]);
      if (!dialogRoot) {
        return false;
      }
      return Boolean(firstMatch([
        ".resume-right-side",
        ".resume-summary"
      ]));
    }

    function extractRecommendSelectionContext() {
      const pageUrl = String((location && location.href) || "");
      if (!pageUrl.includes("/web/frame/recommend/")) {
        return null;
      }
      if (!hasRecommendDetailOverlay()) {
        return null;
      }
      const summaryRoot = firstMatch([".resume-summary", ".resume-item-detail", ".resume-right-side"]);
      const summaryText = collectText(summaryRoot);
      const cards = queryAll(".candidate-card-wrap");
      if (!summaryText || !cards.length) {
        return null;
      }
      const tokens = tokenizeSelectionText(summaryText);
      const pendingSelection = getPendingSelection();
      if (!tokens.length && !pendingSelection) {
        return null;
      }
      let best = null;
      let bestScore = Number.NEGATIVE_INFINITY;
      for (const card of cards) {
        const cardText = collectText(card);
        if (!cardText) {
          continue;
        }
        const hits = tokens.filter(function (token) {
          return cardText.includes(token);
        });
        const snapshot = extractCardSnapshot(card) || {};
        let score = hits.length * 240 + visibilityScore(card);
        if (pendingSelection) {
          if (pendingSelection.geekId && snapshot.geekId && pendingSelection.geekId === snapshot.geekId) {
            score += 12000;
          } else if (pendingSelection.candidateName && snapshot.candidateName && pendingSelection.candidateName === snapshot.candidateName) {
            score += 6000;
          }
        }
        if (cardText.includes("最近关注")) {
          score += 12;
        }
        if (score > bestScore) {
          best = {
            card: card,
            cardText: cardText,
            hits: hits,
            candidateName: snapshot.candidateName || "",
            geekId: snapshot.geekId || ""
          };
          bestScore = score;
        }
      }
      if (!best || bestScore < 240) {
        return null;
      }
      const candidateName = best.candidateName || extractCandidateName(best.cardText, best.card);
      const pageTitle = normalizeText((document && document.title) || "");
      const includeSummary = best.hits && best.hits.length > 0;
      const pageText = normalizeText([
        candidateName,
        best.cardText,
        includeSummary ? "经历概览" : "",
        includeSummary ? summaryText : ""
      ].filter(Boolean).join("\n"));
      const candidateHint = deriveCandidateHint(pageText, best.card, candidateName);
      return {
        ok: true,
        isDetail: true,
        pageUrl: pageUrl,
        pageTitle: pageTitle,
        pageText: pageText,
        candidateName: candidateName,
        candidateHint: candidateHint,
        geekId: best.geekId || "",
        visibilityScore: visibilityScore(best.card) + visibilityScore(summaryRoot),
        observedAt: nowMs(),
        selectionEpoch: pendingSelection ? Number(pendingSelection.selectionEpoch || 0) : currentSelectionEpoch(),
        contextKey: buildCandidateKey({
          pageUrl: pageUrl,
          pageTitle: pageTitle,
          pageText: pageText,
          candidateName: candidateName,
          candidateHint: candidateHint
        })
      };
    }

    function findDetailRoot() {
      const roots = collectDetailRoots();
      let bestRoot = null;
      let bestScore = Number.NEGATIVE_INFINITY;
      for (const candidate of roots) {
        const score = scoreDetailRoot(candidate);
        if (score > bestScore) {
          bestRoot = candidate;
          bestScore = score;
        }
      }
      if (bestRoot) {
        return bestRoot;
      }
      if (document && document.body && isDetailText(collectText(document.body))) {
        return document.body;
      }
      return null;
    }

    const pageUrl = String((location && location.href) || "");
    const pageTitle = normalizeText((document && document.title) || "");
    const recommendSelection = extractRecommendSelectionContext();
    if (recommendSelection) {
      return recommendSelection;
    }
    if (pageUrl.includes("/web/frame/recommend/")) {
      return {
        ok: false,
        isDetail: false,
        reason: "candidate_detail_not_found",
        pageUrl: pageUrl,
        pageTitle: pageTitle
      };
    }
    const detailRoot = findDetailRoot();
    if (!detailRoot || isSimilarSectionActive()) {
      return {
        ok: false,
        isDetail: false,
        reason: "candidate_detail_not_found",
        pageUrl: pageUrl,
        pageTitle: pageTitle
      };
    }

    const pageText = collectText(detailRoot);
    const candidateName = extractCandidateName(pageText, detailRoot);
    const candidateHint = deriveCandidateHint(pageText, detailRoot, candidateName);
    const detailVisibilityScore = visibilityScore(detailRoot);
    return {
      ok: true,
      isDetail: true,
      pageUrl: pageUrl,
      pageTitle: pageTitle,
      pageText: pageText,
      candidateName: candidateName,
      candidateHint: candidateHint,
      geekId: "",
      visibilityScore: detailVisibilityScore,
      observedAt: nowMs(),
      selectionEpoch: currentSelectionEpoch(),
      contextKey: buildCandidateKey({
        pageUrl: pageUrl,
        pageTitle: pageTitle,
        pageText: pageText,
        candidateName: candidateName,
        candidateHint: candidateHint
      })
    };
  }

  function renderScoreBadgeInPage(config, payload) {
    function normalizeText(value) {
      return String(value || "").replace(/\r\n?/g, "\n").trim();
    }

    function queryAll(selector) {
      if (!document || typeof document.querySelectorAll !== "function") {
        return [];
      }
      try {
        return Array.from(document.querySelectorAll(selector) || []);
      } catch (error) {
        return [];
      }
    }

    function firstMatch(selectors) {
      if (!document || typeof document.querySelector !== "function") {
        return null;
      }
      for (const selector of selectors || []) {
        const element = document.querySelector(selector);
        if (element) {
          return element;
        }
      }
      return null;
    }

    function collectText(element) {
      if (!element) {
        return "";
      }
      return normalizeText(element.innerText || element.textContent || "");
    }

    function isDetailText(text) {
      if (!text) {
        return false;
      }
      const keywordHits = (config && config.detailKeywords ? config.detailKeywords : []).filter(function (entry) {
        return text.includes(entry);
      }).length;
      return keywordHits >= 3 || text.length >= 160 || (text.length >= 60 && keywordHits >= 2);
    }

    function collectDetailRoots() {
      const seen = new Set();
      const roots = [];
      for (const selector of (config && config.detailRootSelectors) || []) {
        for (const element of queryAll(selector)) {
          if (!element || seen.has(element)) {
            continue;
          }
          seen.add(element);
          roots.push(element);
        }
      }
      return roots;
    }

    function visibilityScore(element) {
      if (!element) {
        return 0;
      }
      if (typeof window !== "undefined" && window && typeof window.getComputedStyle === "function") {
        try {
          const style = window.getComputedStyle(element);
          if (style && (style.display === "none" || style.visibility === "hidden" || style.opacity === "0")) {
            return -9000;
          }
        } catch (error) {
          // Ignore transient style lookup failures.
        }
      }
      if (typeof element.getBoundingClientRect !== "function") {
        return 0;
      }
      const rect = element.getBoundingClientRect();
      if (!rect || !Number.isFinite(rect.top)) {
        return 0;
      }
      const width = Number(rect.width || 0);
      const height = Number(rect.height || 0);
      if (width <= 1 || height <= 1) {
        return -7000;
      }
      const viewportHeight = Number(
        (typeof window !== "undefined" && window && window.innerHeight)
        || (document && document.documentElement && document.documentElement.clientHeight)
        || 0
      );
      if (!viewportHeight) {
        return 0;
      }
      const top = Number(rect.top);
      const bottom = Number(rect.bottom !== undefined ? rect.bottom : (rect.top + height));
      if (bottom <= 0 || top >= viewportHeight) {
        return -3200;
      }
      let score = 3600;
      const visibleTop = Math.max(0, top);
      const visibleBottom = Math.min(viewportHeight, bottom);
      const visibleHeight = Math.max(0, visibleBottom - visibleTop);
      if (top >= -80 && top <= viewportHeight * 0.42) {
        score += 900;
      }
      if (visibleHeight >= Math.min(height, viewportHeight * 0.45)) {
        score += 1200;
      }
      return score;
    }

    function scoreDetailRoot(element) {
      const text = collectText(element);
      if (!isDetailText(text)) {
        return Number.NEGATIVE_INFINITY;
      }
      const keywordHits = ((config && config.detailKeywords) || []).filter(function (entry) {
        return text.includes(entry);
      }).length;
      let score = keywordHits * 100 + Math.min(text.length, 4000);
      score += visibilityScore(element);
      if (text.includes("工作经历")) {
        score += 280;
      }
      if (text.includes("教育经历")) {
        score += 220;
      }
      if (text.includes("期望职位")) {
        score += 120;
      }
      if (/^[\u4e00-\u9fa5·*]{2,8}\n.*(岁|年|本科|硕士|博士|大专|专科|到岗|离职|在职)/.test(text)) {
        score += 260;
      }
      if (text.includes("其他相似经历的牛人")) {
        score -= 480;
      }
      return score;
    }

    function findSimilarSectionAnchor() {
      const titles = (shared && shared.SIMILAR_SECTION_TITLES) || [];
      const candidates = queryAll("h1,h2,h3,h4,strong,div,span,p");
      for (const title of titles) {
        let bestMatch = null;
        let bestLength = Number.POSITIVE_INFINITY;
        for (const element of candidates) {
          const text = collectText(element);
          if (!text || text.indexOf(title) === -1) {
            continue;
          }
          if (text === title) {
            return element;
          }
          if (text.length < bestLength) {
            bestMatch = element;
            bestLength = text.length;
          }
        }
        if (bestMatch) {
          return bestMatch;
        }
      }
      return null;
    }

    function isSimilarSectionActive() {
      const anchor = findSimilarSectionAnchor();
      if (!anchor || typeof anchor.getBoundingClientRect !== "function") {
        return false;
      }
      const rect = anchor.getBoundingClientRect();
      const viewportHeight = Number(
        (typeof window !== "undefined" && window && window.innerHeight)
        || (document && document.documentElement && document.documentElement.clientHeight)
        || 0
      );
      if (!Number.isFinite(rect.top)) {
        return false;
      }
      if (!viewportHeight) {
        return rect.top <= 320;
      }
      return rect.top <= viewportHeight * 0.55;
    }

    function findDetailRoot() {
      const roots = collectDetailRoots();
      let bestRoot = null;
      let bestScore = Number.NEGATIVE_INFINITY;
      for (const candidate of roots) {
        const score = scoreDetailRoot(candidate);
        if (score > bestScore) {
          bestRoot = candidate;
          bestScore = score;
        }
      }
      if (bestRoot) {
        return bestRoot;
      }
      if (document && document.body && isDetailText(collectText(document.body))) {
        return document.body;
      }
      return null;
    }

    function isRecommendDoc() {
      return String((location && location.href) || "").includes("/web/frame/recommend/");
    }

    function findRecommendBadgeMountRoot() {
      return firstMatch([".resume-right-side", ".resume-simple-box", ".resume-item-detail", ".boss-popup__content"]);
    }

    function resolveBadgeMountRoot(detailRoot) {
      if (isRecommendDoc()) {
        return findRecommendBadgeMountRoot() || detailRoot;
      }
      return detailRoot;
    }

    function localizeDecision(decision) {
      const labels = {
        recommend: "推荐",
        review: "待复核",
        reject: "不推荐",
        pending: "待处理"
      };
      return labels[decision] || decision || labels.pending;
    }

    if (String((location && location.href) || "").includes("/web/frame/recommend/")) {
      const existing = document.getElementById ? document.getElementById("boss-resume-score-badge") : null;
      if (existing && typeof existing.remove === "function") {
        existing.remove();
      }
      return { ok: false, reason: "candidate_detail_not_found" };
    }

    const detailRoot = findDetailRoot();
    const mountRoot = resolveBadgeMountRoot(detailRoot);
    if (!detailRoot || !mountRoot || isSimilarSectionActive() || typeof mountRoot.prepend !== "function") {
      return { ok: false, reason: "candidate_detail_not_found" };
    }

    const badgeId = "boss-resume-score-badge";
    let badge = document.getElementById ? document.getElementById(badgeId) : null;
    if (!badge) {
      badge = document.createElement("div");
      badge.id = badgeId;
    }
    if (badge.parentElement !== mountRoot) {
      mountRoot.prepend(badge);
    }
    badge.style.cssText = [
      "margin: 0 0 12px 0",
      "padding: 10px 12px",
      isRecommendDoc() ? "border-radius: 14px" : "border-radius: 12px",
      "font-family: -apple-system, BlinkMacSystemFont, sans-serif",
      isRecommendDoc() ? "font-size: 12px" : "font-size: 13px",
      isRecommendDoc() ? "line-height: 1.45" : "line-height: 1.5",
      "background: linear-gradient(135deg, rgba(4,121,255,.12), rgba(0,190,189,.12))",
      "border: 1px solid rgba(4,121,255,.22)",
      "color: #17324d",
      "display: block",
      "width: 100%",
      "max-width: 100%",
      "box-sizing: border-box",
      "align-self: stretch",
      isRecommendDoc() ? "box-shadow: 0 10px 24px rgba(23,50,77,.08)" : ""
    ].filter(Boolean).join(";");

    const toneColor = payload && payload.decision === "recommend"
      ? "#0c8a4d"
      : payload && payload.decision === "review"
        ? "#a66300"
        : payload && payload.decision === "reject"
          ? "#b42318"
          : "#475467";
    const reason = (payload && payload.review_reasons && payload.review_reasons[0]) || (payload && payload.hard_filter_fail_reasons && payload.hard_filter_fail_reasons[0]) || "";
    badge.innerHTML = [
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">',
      '<div><strong style="font-size:14px;">系统评分</strong><div style="opacity:.72;">本地筛选后端</div></div>',
      '<div style="text-align:right;">',
      '<div style="font-size:22px;font-weight:700;">' + String(payload && payload.score !== undefined ? payload.score : "-") + "</div>",
      '<div style="color:' + toneColor + ';font-weight:600;">' + localizeDecision((payload && payload.decision) || "pending") + '</div>',
      "</div>",
      "</div>",
      reason ? '<div style="margin-top:8px;opacity:.84;">' + shared.shortText(reason, isRecommendDoc() ? 56 : 120) + "</div>" : "",
      payload && payload.fallback_used ? '<div style="margin-top:6px;color:#a66300;">已降级为启发式打分</div>' : ""
    ].join("");
    return { ok: true };
  }

  function extractBossSessionSnapshotInPage() {
    function normalizeText(value) {
      return String(value || "")
        .replace(/\r\n?/g, "\n")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n{3,}/g, "\n\n")
        .replace(/[ \t]{2,}/g, " ")
        .trim();
    }

    const bodyText = normalizeText(
      (document && document.body && (document.body.innerText || document.body.textContent)) || ""
    ).slice(0, 5000);
    return {
      current_url: String((window && window.location && window.location.href) || ""),
      page_title: String((document && document.title) || ""),
      body_text: bodyText,
      recruiter_markers: ["职位管理", "推荐牛人", "沟通", "牛人管理", "面试", "人才库"].filter(function (marker) {
        return bodyText.indexOf(marker) >= 0;
      }),
      login_markers: ["扫码登录", "登录/注册", "验证码登录/注册", "当前登录状态已失效"].filter(function (marker) {
        return bodyText.indexOf(marker) >= 0;
      })
    };
  }

  function createScoreService(options) {
    const storage = options && options.storage;
    const prefsStorage = options && options.prefsStorage;
    const fetchImpl = (options && options.fetchImpl) || root.fetch.bind(root);
    const fallbackBackendBaseUrl = (options && options.backendBaseUrl) || BACKEND_BASE_URL;

    async function getBackendBaseUrl() {
      if (!prefsStorage) {
        return fallbackBackendBaseUrl;
      }
      const prefs = await prefsStorage.get(shared.PREFS_STORAGE_KEY);
      return shared.normalizeBackendBaseUrl(prefs && prefs.backendBaseUrl) || fallbackBackendBaseUrl;
    }

    async function listJobs() {
      try {
        const backendBaseUrl = await getBackendBaseUrl();
        const paths = ["/api/scoring-targets", "/api/jobs"];
        for (const path of paths) {
          const response = await fetchImpl(backendBaseUrl + path, {
            method: "GET"
          });
          if (!response.ok) {
            continue;
          }
          const payload = await response.json();
          const items = Array.isArray(payload && payload.items) ? payload.items : [];
          if (!items.length) {
            continue;
          }
          return items.map(function (item) {
            return {
              id: item.id,
              name: item.name
            };
          });
        }
        return shared.JOB_OPTIONS_FALLBACK.slice();
      } catch (error) {
        return shared.JOB_OPTIONS_FALLBACK.slice();
      }
    }

    async function scoreContext(args) {
      const jobId = args && args.jobId;
      const context = (args && args.context) || {};
      const candidateId = args && args.candidateId;
      const force = Boolean(args && args.force);
      if (!jobId) {
        throw new Error("job_id_required");
      }
      if (!shared.normalizeText(context.pageText)) {
        throw new Error("candidate_detail_missing");
      }

      const cacheKey = buildCacheKey(jobId, context);
      if (!force) {
        const cached = storage ? await storage.get(cacheKey) : undefined;
        if (cached) {
          return Object.assign({}, cached, { cacheHit: true, cacheKey: cacheKey });
        }
      }

      const backendBaseUrl = await getBackendBaseUrl();
      const response = await fetchImpl(candidateId
        ? backendBaseUrl + "/api/extension/candidates/" + encodeURIComponent(candidateId) + "/score"
        : backendBaseUrl + "/api/extension/score", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          job_id: jobId,
          page_url: context.pageUrl,
          page_title: context.pageTitle,
          page_text: context.pageText,
          candidate_hint: context.candidateName || context.candidateHint,
          source: "boss_extension_v1"
        })
      });
      let payload = {};
      try {
        payload = await response.json();
      } catch (error) {
        payload = {};
      }
      if (!response.ok) {
        throw new Error(payload.error || "extension_score_failed");
      }
      const storedPayload = Object.assign({}, payload, {
        candidate_id: payload.candidate_id || candidateId || "",
        cacheKey: cacheKey,
        cachedAt: new Date().toISOString(),
        jobId: jobId
      });
      if (storage) {
        await storage.set({ [cacheKey]: storedPayload });
      }
      return Object.assign({}, storedPayload, { cacheHit: false });
    }

    return {
      buildCacheKey,
      listJobs,
      scoreContext
    };
  }

  function createCandidateService(options) {
    const storage = options && options.storage;
    const prefsStorage = options && options.prefsStorage;
    const fetchImpl = (options && options.fetchImpl) || root.fetch.bind(root);
    const fallbackBackendBaseUrl = (options && options.backendBaseUrl) || BACKEND_BASE_URL;

    function buildCandidateCacheKey(jobId, context) {
      return "boss_resume_candidate:" + String(jobId || "") + ":" + shared.buildCandidateKey(context || {});
    }

    function buildSourceCandidateKey(jobId, context) {
      const geekId = String((context && context.geekId) || "").trim();
      if (geekId) {
        return geekId;
      }
      const pageUrl = String((context && context.pageUrl) || "");
      const matched = pageUrl.match(/(?:[?&])(geekId|gid|uid|id)=([A-Za-z0-9_-]{4,})/i);
      if (matched && matched[2]) {
        return matched[2];
      }
      return shared.buildCandidateKey(
        Object.assign(
          { jobId: jobId || "" },
          context || {}
        )
      );
    }

    async function getPrefs() {
      const payload = prefsStorage ? await prefsStorage.get(shared.PREFS_STORAGE_KEY) : undefined;
      if (payload && typeof payload === "object") {
        return payload;
      }
      return {};
    }

    async function getBackendBaseUrl() {
      const prefs = await getPrefs();
      return shared.normalizeBackendBaseUrl(prefs && prefs.backendBaseUrl) || fallbackBackendBaseUrl;
    }

    async function getDefaultJobId() {
      const prefs = await getPrefs();
      return String((prefs && prefs.jobId) || "qa_test_engineer_v1");
    }

    async function ensureCandidateForContext(args) {
      const jobId = String((args && args.jobId) || await getDefaultJobId() || "").trim();
      const context = (args && args.context) || {};
      const force = Boolean(args && args.force);
      if (!jobId) {
        throw new Error("job_id_required");
      }
      if (!shared.normalizeText(context.pageText)) {
        throw new Error("candidate_detail_missing");
      }
      const cacheKey = buildCandidateCacheKey(jobId, context);
      if (!force) {
        const cached = storage ? await storage.get(cacheKey) : undefined;
        if (cached && cached.candidate_id) {
          return Object.assign({}, cached, { cacheHit: true, cacheKey: cacheKey });
        }
      }
      const backendBaseUrl = await getBackendBaseUrl();
      const response = await fetchImpl(backendBaseUrl + "/api/extension/candidates/upsert", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          job_id: jobId,
          source: "boss_extension_v1",
          source_candidate_key: buildSourceCandidateKey(jobId, context),
          external_id: String((context && context.geekId) || "").trim() || undefined,
          page_url: context.pageUrl,
          page_title: context.pageTitle,
          page_text: context.pageText,
          candidate_name: context.candidateName || context.candidateHint,
          page_type: "boss_resume_detail",
          observed_at: new Date(Number((context && context.observedAt) || Date.now())).toISOString(),
          context_key: context.contextKey || shared.buildCandidateKey(context),
          quick_fit_payload: shared.analyzeQuickFit(jobId, context.pageText || "")
        })
      });
      let payload = {};
      try {
        payload = await response.json();
      } catch (error) {
        payload = {};
      }
      if (!response.ok) {
        throw new Error(payload.error || "candidate_sync_failed");
      }
      const storedPayload = Object.assign({}, payload, {
        cacheKey: cacheKey,
        jobId: jobId,
        cachedAt: new Date().toISOString()
      });
      if (storage) {
        await storage.set({ [cacheKey]: storedPayload });
      }
      return Object.assign({}, storedPayload, { cacheHit: false });
    }

    async function saveStage(args) {
      const candidateId = String((args && args.candidateId) || "").trim();
      const payload = Object.assign({}, (args && args.payload) || {});
      if (!candidateId) {
        throw new Error("candidate_sync_failed");
      }
      const backendBaseUrl = await getBackendBaseUrl();
      const response = await fetchImpl(backendBaseUrl + "/api/candidates/" + encodeURIComponent(candidateId) + "/stage", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        data = {};
      }
      if (!response.ok) {
        throw new Error(data.error || "candidate_stage_save_failed");
      }
      return data;
    }

    async function storeCandidateRecord(jobId, context, record) {
      if (!storage || !jobId || !context || !record) {
        return;
      }
      await storage.set({
        [buildCandidateCacheKey(jobId, context)]: Object.assign({}, record, {
          jobId: jobId,
          cachedAt: new Date().toISOString()
        })
      });
    }

    return {
      buildCandidateCacheKey,
      buildSourceCandidateKey,
      ensureCandidateForContext,
      getDefaultJobId,
      saveStage,
      storeCandidateRecord
    };
  }

  function isBossUrl(url) {
    return /^https:\/\/www\.zhipin\.com\//.test(String(url || ""));
  }

  async function queryActiveTab(chromeApi) {
    const tabs = await callbackToPromise(function (done) {
      chromeApi.tabs.query({ active: true, currentWindow: true }, done);
    });
    return Array.isArray(tabs) && tabs.length ? tabs[0] : null;
  }

  async function getFrameDescriptors(chromeApi, tabId) {
    if (!chromeApi.webNavigation || typeof chromeApi.webNavigation.getAllFrames !== "function") {
      return [{ frameId: 0 }];
    }
    try {
      const frames = await callbackToPromise(function (done) {
        chromeApi.webNavigation.getAllFrames({ tabId: tabId }, done);
      });
      return Array.isArray(frames) && frames.length ? frames : [{ frameId: 0 }];
    } catch (error) {
      return [{ frameId: 0 }];
    }
  }

  async function sendMessageToFrame(chromeApi, tabId, frameId, message) {
    return callbackToPromise(function (done) {
      chromeApi.tabs.sendMessage(tabId, message, { frameId: frameId }, done);
    });
  }

  async function ensureContentScriptInjected(chromeApi, tabId) {
    if (!chromeApi.scripting || typeof chromeApi.scripting.executeScript !== "function") {
      return false;
    }
    try {
      await callbackToPromise(function (done) {
        chromeApi.scripting.executeScript(
          {
            target: { tabId: tabId, allFrames: true },
            files: ["shared.js", "content-script.js"]
          },
          done
        );
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  async function executeScript(chromeApi, payload) {
    return callbackToPromise(function (done) {
      chromeApi.scripting.executeScript(payload, done);
    });
  }

  async function collectContextsViaScripting(chromeApi, tabId) {
    if (!chromeApi.scripting || typeof chromeApi.scripting.executeScript !== "function") {
      return [];
    }
    try {
      const results = await executeScript(chromeApi, {
        target: { tabId: tabId, allFrames: true },
        func: extractPageContextInPage,
        args: [createPageContextConfig()]
      });
      return (results || [])
        .map(function (entry) {
          const result = entry && entry.result ? entry.result : null;
          if (!result) {
            return null;
          }
          return Object.assign({}, result, { frameId: entry.frameId || 0 });
        })
        .filter(function (entry) {
          return entry && entry.isDetail && entry.pageText;
        });
    } catch (error) {
      return [];
    }
  }

  async function collectContexts(chromeApi, tabId) {
    const scriptedContexts = await collectContextsViaScripting(chromeApi, tabId);
    if (scriptedContexts.length) {
      return scriptedContexts;
    }
    const frames = await getFrameDescriptors(chromeApi, tabId);
    const contexts = [];
    for (const frame of frames) {
      try {
        const response = await sendMessageToFrame(chromeApi, tabId, frame.frameId, {
          type: "boss_resume_score:get-page-context"
        });
        if (response && response.isDetail && response.pageText) {
          contexts.push(response);
        }
      } catch (error) {
        // Ignore missing listeners or unsupported frames.
      }
    }
    return contexts;
  }

  async function getActiveContext(chromeApi, liveContextsByTab) {
    const tab = await queryActiveTab(chromeApi);
    if (!tab || !isBossUrl(tab.url)) {
      throw new Error("boss_tab_not_found");
    }
    let contexts = collectLiveContexts(liveContextsByTab, tab.id);
    if (!contexts.length) {
      contexts = await collectContexts(chromeApi, tab.id);
      contexts.forEach(function (context) {
        rememberLiveContext(liveContextsByTab, tab.id, context.frameId || 0, context);
      });
    }
    if (!contexts.length) {
      const injected = await ensureContentScriptInjected(chromeApi, tab.id);
      if (injected) {
        contexts = await collectContexts(chromeApi, tab.id);
        contexts.forEach(function (context) {
          rememberLiveContext(liveContextsByTab, tab.id, context.frameId || 0, context);
        });
      }
    }
    if (!contexts.length) {
      throw new Error("candidate_detail_not_found");
    }
    const bestContext = pickBestContext(contexts);
    if (!bestContext) {
      throw new Error("candidate_detail_not_found");
    }
    return {
      tabId: tab.id,
      frameId: bestContext.frameId || 0,
      context: bestContext
    };
  }

  async function renderBadgeViaScripting(chromeApi, tabId, frameId, payload) {
    if (!chromeApi.scripting || typeof chromeApi.scripting.executeScript !== "function") {
      return false;
    }
    try {
      await executeScript(chromeApi, {
        target: { tabId: tabId, frameIds: [frameId] },
        func: renderScoreBadgeInPage,
        args: [createPageContextConfig(), payload]
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  async function sendBadgeMessage(chromeApi, tabId, frameId, message) {
    try {
      await sendMessageToFrame(chromeApi, tabId, frameId, message);
      return true;
    } catch (error) {
      const injected = await ensureContentScriptInjected(chromeApi, tabId);
      if (!injected) {
        return false;
      }
      try {
        await sendMessageToFrame(chromeApi, tabId, frameId, message);
        return true;
      } catch (retryError) {
        return false;
      }
    }
  }

  async function syncSidePanelForTab(chromeApi, tabId, tab) {
    if (!chromeApi.sidePanel || typeof chromeApi.sidePanel.setOptions !== "function") {
      return;
    }
    try {
      await callbackToPromise(function (done) {
        chromeApi.sidePanel.setOptions(
          {
            tabId: tabId,
            path: "sidepanel.html",
            enabled: Boolean(tab && isBossUrl(tab.url))
          },
          done
        );
      });
    } catch (error) {
      // Ignore side panel option errors to keep the worker resilient.
    }
  }

  function enrichContextWithCandidate(context, candidateRecord) {
    if (!context || !candidateRecord) {
      return context;
    }
    return Object.assign({}, context, {
      candidateId: candidateRecord.candidate_id || candidateRecord.candidateId || "",
      taskId: candidateRecord.task_id || "",
      pipelineState: candidateRecord.pipeline_state || candidateRecord.pipelineState || null,
      manualStageLocked: Boolean(
        candidateRecord.manual_stage_locked
        || (candidateRecord.pipeline_state && candidateRecord.pipeline_state.manual_stage_locked)
      )
    });
  }

  async function collectBossSessionSnapshot(chromeApi, tabId) {
    if (!chromeApi.scripting || typeof chromeApi.scripting.executeScript !== "function") {
      return null;
    }
    try {
      const results = await executeScript(chromeApi, {
        target: { tabId: tabId, allFrames: false },
        func: extractBossSessionSnapshotInPage
      });
      const result = results && results[0] && results[0].result;
      return result || null;
    } catch (error) {
      return null;
    }
  }

  async function ensureActiveCandidate(chromeApi, liveContextsByTab, candidateService, args) {
    const active = await getActiveContext(chromeApi, liveContextsByTab);
    const candidateRecord = await candidateService.ensureCandidateForContext({
      jobId: args && args.jobId,
      context: active.context,
      force: Boolean(args && args.force)
    });
    const nextContext = enrichContextWithCandidate(active.context, candidateRecord);
    rememberLiveContext(liveContextsByTab, active.tabId, active.frameId || 0, nextContext);
    return {
      tabId: active.tabId,
      frameId: active.frameId || 0,
      context: nextContext,
      candidate: candidateRecord
    };
  }

  function register(chromeApi) {
    const storage = createStorageAdapter(chromeApi.storage && chromeApi.storage.session);
    const prefsStorage = createStorageAdapter(chromeApi.storage && chromeApi.storage.local);
    const fetchImpl = root.fetch.bind(root);
    const scoreService = createScoreService({
      storage: storage,
      prefsStorage: prefsStorage,
      fetchImpl: fetchImpl,
      backendBaseUrl: BACKEND_BASE_URL
    });
    const candidateService = createCandidateService({
      storage: storage,
      prefsStorage: prefsStorage,
      fetchImpl: fetchImpl,
      backendBaseUrl: BACKEND_BASE_URL
    });
    const liveContextsByTab = {};
    const ingestTimers = {};
    let bossSessionSyncInFlight = null;
    let bossSessionSyncFingerprint = "";
    let bossSessionSyncedAt = 0;

    async function getBackendBaseUrl() {
      const prefs = prefsStorage ? await prefsStorage.get("boss_resume_score:prefs") : undefined;
      return shared.normalizeBackendBaseUrl(prefs && prefs.backendBaseUrl) || BACKEND_BASE_URL;
    }

    function ingestTimerKey(tabId, frameId) {
      return String(tabId) + ":" + String(frameId || 0);
    }

    function notifyContextUpdate(tabId, frameId, context) {
      try {
        chromeApi.runtime.sendMessage({
          type: "boss_resume_score:page-context-updated",
          tabId: tabId,
          frameId: frameId || 0,
          context: context || null
        });
      } catch (error) {
        // Side panel refresh signal is best-effort only.
      }
    }

    function buildBossCookieFingerprint(cookies) {
      return JSON.stringify(
        (cookies || [])
          .map(function (cookie) {
            return [
              String(cookie.domain || ""),
              String(cookie.path || "/"),
              String(cookie.name || ""),
              String(cookie.value || ""),
              Number(cookie.expirationDate || -1)
            ];
          })
          .sort(function (left, right) {
            return JSON.stringify(left).localeCompare(JSON.stringify(right));
          })
      );
    }

    async function listBossCookies() {
      if (!chromeApi.cookies || typeof chromeApi.cookies.getAll !== "function") {
        return [];
      }
      const cookies = await callbackToPromise(function (done) {
        chromeApi.cookies.getAll({ domain: "zhipin.com" }, done);
      });
      return (cookies || []).filter(function (cookie) {
        return cookie && cookie.name && cookie.domain;
      });
    }

    async function syncBossSession(tab, reason) {
      return {
        ok: true,
        skipped: true,
        reason: "manual_login_mode",
        message: "Session sync is disabled. Manual login plus current-page capture is now the default flow."
      };
    }

    function scheduleCandidateIngest(tabId, frameId, context) {
      if (tabId === undefined || !context || !context.isDetail || !context.pageText) {
        return;
      }
      const timerKey = ingestTimerKey(tabId, frameId);
      if (ingestTimers[timerKey]) {
        root.clearTimeout(ingestTimers[timerKey]);
      }
      ingestTimers[timerKey] = root.setTimeout(async function () {
        delete ingestTimers[timerKey];
        const currentContexts = collectLiveContexts(liveContextsByTab, tabId);
        const latest = currentContexts.find(function (entry) {
          return Number(entry.frameId || 0) === Number(frameId || 0);
        });
        if (!latest || !latest.isDetail || latest.contextKey !== context.contextKey) {
          return;
        }
        try {
          const candidateRecord = await candidateService.ensureCandidateForContext({
            context: latest,
            jobId: await candidateService.getDefaultJobId(),
            force: false
          });
          const nextContext = enrichContextWithCandidate(latest, candidateRecord);
          rememberLiveContext(liveContextsByTab, tabId, frameId, nextContext);
          notifyContextUpdate(tabId, frameId, nextContext);
        } catch (error) {
          // Auto-ingest is best-effort. Side panel can still retry on refresh.
        }
      }, 650);
    }

    chromeApi.runtime.onMessage.addListener(function (message, sender, sendResponse) {
      if (!message || !message.type) {
        return undefined;
      }
      (async function () {
        if (message.type === "boss_resume_score:get-jobs") {
          return { ok: true, items: await scoreService.listJobs() };
        }
        if (message.type === "boss_resume_score:get-active-context") {
          const payload = message.jobId
            ? await ensureActiveCandidate(chromeApi, liveContextsByTab, candidateService, {
              jobId: message.jobId,
              force: Boolean(message.force)
            })
            : await getActiveContext(chromeApi, liveContextsByTab);
          return Object.assign({ ok: true }, payload);
        }
        if (message.type === "boss_resume_score:sync-boss-session") {
          return {
            ok: true,
            skipped: true,
            reason: "manual_login_mode",
            message: "Session sync is disabled. Manual login plus current-page capture is now the default flow."
          };
        }
        if (message.type === "boss_resume_score:page-context-signal") {
          if (sender && sender.tab && sender.tab.id !== undefined) {
            const payload = message.payload || null;
            rememberLiveContext(
              liveContextsByTab,
              sender.tab.id,
              sender.frameId || 0,
              payload
            );
            notifyContextUpdate(sender.tab.id, sender.frameId || 0, payload);
            if (payload && payload.isDetail && payload.pageText) {
              scheduleCandidateIngest(sender.tab.id, sender.frameId || 0, payload);
            }
          }
          return { ok: true };
        }
        if (message.type === "boss_resume_score:page-context-updated") {
          return { ok: true };
        }
        if (message.type === "boss_resume_score:save-stage") {
          const result = await candidateService.saveStage({
            candidateId: message.candidateId,
            payload: message.payload
          });
          const active = message.context && message.tabId !== undefined
            ? { tabId: message.tabId, frameId: message.frameId || 0, context: message.context }
            : await getActiveContext(chromeApi, liveContextsByTab);
          const nextContext = enrichContextWithCandidate(active.context, {
            candidate_id: message.candidateId,
            pipeline_state: result.state || null,
            manual_stage_locked: true
          });
          rememberLiveContext(liveContextsByTab, active.tabId, active.frameId || 0, nextContext);
          await candidateService.storeCandidateRecord(message.jobId, nextContext, {
            candidate_id: message.candidateId,
            pipeline_state: result.state || null,
            manual_stage_locked: true
          });
          notifyContextUpdate(active.tabId, active.frameId || 0, nextContext);
          return Object.assign({ ok: true, tabId: active.tabId, frameId: active.frameId, context: nextContext }, result);
        }
        if (message.type === "boss_resume_score:render-quick-fit") {
          const active = message.context && message.tabId !== undefined
            ? { tabId: message.tabId, frameId: message.frameId || 0, context: message.context }
            : await getActiveContext(chromeApi, liveContextsByTab);
          await sendBadgeMessage(chromeApi, active.tabId, active.frameId, {
            type: "boss_resume_score:show-quick-fit",
            payload: Object.assign(
              {
                jobLabel: shared.localizeJobName(message.jobId)
              },
              message.analysis || shared.analyzeQuickFit(message.jobId, active.context && active.context.pageText)
            )
          });
          return { ok: true };
        }
        if (message.type === "boss_resume_score:clear-quick-fit") {
          if (message.tabId === undefined) {
            return { ok: true };
          }
          await sendBadgeMessage(chromeApi, message.tabId, message.frameId || 0, {
            type: "boss_resume_score:clear-quick-fit"
          });
          return { ok: true };
        }
        if (message.type === "boss_resume_score:score-active-context") {
          const active = message.context && message.tabId !== undefined
            ? {
              tabId: message.tabId,
              frameId: message.frameId || 0,
              context: message.context.candidateId
                ? message.context
                : enrichContextWithCandidate(
                  message.context,
                  await candidateService.ensureCandidateForContext({
                    jobId: message.jobId,
                    context: message.context,
                    force: false
                  })
                )
            }
            : await ensureActiveCandidate(chromeApi, liveContextsByTab, candidateService, {
              jobId: message.jobId,
              force: false
            });
          const result = await scoreService.scoreContext({
            jobId: message.jobId,
            context: active.context,
            candidateId: active.context && active.context.candidateId,
            force: Boolean(message.force)
          });
          const nextContext = enrichContextWithCandidate(active.context, {
            candidate_id: result.candidate_id || (active.context && active.context.candidateId),
            pipeline_state: result.pipeline_state || (active.context && active.context.pipelineState) || null,
            manual_stage_locked: result.manual_stage_locked
          });
          rememberLiveContext(liveContextsByTab, active.tabId, active.frameId || 0, nextContext);
          await candidateService.storeCandidateRecord(message.jobId, nextContext, {
            candidate_id: result.candidate_id || nextContext.candidateId,
            pipeline_state: result.pipeline_state || nextContext.pipelineState || null,
            manual_stage_locked: result.manual_stage_locked
          });
          notifyContextUpdate(active.tabId, active.frameId || 0, nextContext);
          try {
            const scripted = await renderBadgeViaScripting(chromeApi, active.tabId, active.frameId, result);
            if (!scripted) {
              await sendMessageToFrame(chromeApi, active.tabId, active.frameId, {
                type: "boss_resume_score:show-score",
                payload: result
              });
            }
          } catch (error) {
            // Badge rendering is best-effort only.
          }
          return Object.assign({ ok: true, tabId: active.tabId, frameId: active.frameId, context: nextContext }, result);
        }
        throw new Error("unsupported_message");
      })()
        .then(function (payload) {
          sendResponse(payload);
        })
        .catch(function (error) {
          sendResponse({ ok: false, error: error.message || String(error) });
        });
      return true;
    });

    if (chromeApi.tabs && chromeApi.tabs.onUpdated) {
      chromeApi.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
        if (changeInfo && changeInfo.status === "complete") {
          syncSidePanelForTab(chromeApi, tabId, tab);
        }
      });
    }

    if (chromeApi.tabs && chromeApi.tabs.onActivated) {
      chromeApi.tabs.onActivated.addListener(function (activeInfo) {
        chromeApi.tabs.get(activeInfo.tabId, function (tab) {
          syncSidePanelForTab(chromeApi, activeInfo.tabId, tab);
        });
      });
    }

    if (chromeApi.action && chromeApi.action.onClicked && chromeApi.sidePanel && chromeApi.sidePanel.open) {
      chromeApi.action.onClicked.addListener(function (tab) {
        if (!tab || tab.windowId === undefined) {
          return;
        }
        chromeApi.sidePanel.open({ windowId: tab.windowId });
      });
    }
  }

  return {
    BACKEND_BASE_URL,
    buildCacheKey,
    collectLiveContexts,
    createCandidateService,
    createStorageAdapter,
    createScoreService,
    getActiveContext,
    isBossUrl,
    pickBestContext,
    rememberLiveContext,
    register
  };
});
