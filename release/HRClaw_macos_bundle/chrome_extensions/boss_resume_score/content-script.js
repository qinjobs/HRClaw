(function (root, factory) {
  const api = factory(root, root.BossResumeScoreShared || (typeof require === "function" ? require("./shared.js") : null));
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BossResumeScoreContentScript = api;
  if (!root.__BOSS_RESUME_SCORE_DISABLE_AUTO_INIT__ && root.chrome && root.chrome.runtime && root.chrome.runtime.onMessage) {
    api.register(root.chrome);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (root, shared) {
  const BADGE_ID = "boss-resume-score-badge";
  const QUICK_BADGE_ID = "boss-resume-quick-fit-badge";
  const CONTEXT_SIGNAL_DELAY_MS = 140;
  const PENDING_SELECTION_TTL_MS = 2600;

  function firstMatch(doc, selectors) {
    if (!doc || typeof doc.querySelector !== "function") {
      return null;
    }
    for (const selector of selectors || []) {
      const element = doc.querySelector(selector);
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
    return shared.normalizeText(element.innerText || element.textContent || "");
  }

  function queryAll(doc, selector) {
    if (!doc || typeof doc.querySelectorAll !== "function") {
      return [];
    }
    try {
      return Array.from(doc.querySelectorAll(selector) || []);
    } catch (error) {
      return [];
    }
  }

  function normalizeCandidateName(value) {
    return shared.normalizeCandidateNameText(value);
  }

  function findLikelyCandidateName(value) {
    return shared.extractCandidateNameFragment(value);
  }

  function candidateNameFromText(pageText) {
    const lines = shared.normalizeText(pageText)
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

  function extractCandidateName(doc, pageText, detailRoot) {
    const textName = candidateNameFromText(pageText);
    if (textName) {
      return textName;
    }

    const scopedHintElement = detailRoot && typeof detailRoot.querySelector === "function"
      ? firstMatch(detailRoot, shared.HINT_SELECTORS)
      : null;
    const scopedHintText = findLikelyCandidateName(collectText(scopedHintElement));
    if (scopedHintText) {
      return scopedHintText;
    }

    const safeGlobalSelectors = [".name-label", ".candidate-head .name", ".geek-name", ".resume-top-wrap .name"];
    const hintElement = firstMatch(doc, safeGlobalSelectors);
    return findLikelyCandidateName(collectText(hintElement));
  }

  function isDetailText(text) {
    if (!text) {
      return false;
    }
    const keywordHits = shared.DETAIL_KEYWORDS.filter((entry) => text.includes(entry)).length;
    return keywordHits >= 3 || text.length >= 160 || (text.length >= 60 && keywordHits >= 2);
  }

  function collectDetailRoots(doc) {
    const seen = new Set();
    const roots = [];
    for (const selector of shared.DETAIL_ROOT_SELECTORS || []) {
      for (const element of queryAll(doc, selector)) {
        if (!element || seen.has(element)) {
          continue;
        }
        seen.add(element);
        roots.push(element);
      }
    }
    return roots;
  }

  function visibilityScore(element, doc) {
    if (!element) {
      return 0;
    }
    const ownerDoc = doc || element.ownerDocument || null;
    const view = (ownerDoc && ownerDoc.defaultView) || root || null;
    if (view && typeof view.getComputedStyle === "function") {
      try {
        const style = view.getComputedStyle(element);
        if (!style) {
          return 0;
        }
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
          return -9000;
        }
      } catch (error) {
        // Ignore style lookup errors from transient nodes.
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
      (view && view.innerHeight)
      || (ownerDoc && ownerDoc.documentElement && ownerDoc.documentElement.clientHeight)
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

  function scoreDetailRoot(element, doc) {
    const text = collectText(element);
    if (!isDetailText(text)) {
      return Number.NEGATIVE_INFINITY;
    }
    const keywordHits = shared.DETAIL_KEYWORDS.filter((entry) => text.includes(entry)).length;
    let score = keywordHits * 100 + Math.min(text.length, 4000);
    score += visibilityScore(element, doc);
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

  function findSimilarSectionAnchor(doc) {
    const titles = shared.SIMILAR_SECTION_TITLES || [];
    const candidates = queryAll(doc, "h1,h2,h3,h4,strong,div,span,p");
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

  function isSimilarSectionActive(doc) {
    const anchor = findSimilarSectionAnchor(doc);
    if (!anchor || typeof anchor.getBoundingClientRect !== "function") {
      return false;
    }
    const rect = anchor.getBoundingClientRect();
    const viewportHeight = Number(
      (root && root.innerHeight)
      || (doc && doc.documentElement && doc.documentElement.clientHeight)
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

  function deriveCandidateHint(doc, pageText, detailRoot, candidateName) {
    if (candidateName) {
      return shared.shortText(candidateName, 80);
    }

    const scopedHintElement = detailRoot && typeof detailRoot.querySelector === "function"
      ? firstMatch(detailRoot, shared.HINT_SELECTORS)
      : null;
    const scopedHintText = findLikelyCandidateName(collectText(scopedHintElement));
    if (scopedHintText) {
      return shared.shortText(scopedHintText, 80);
    }

    const hintElement = firstMatch(doc, shared.HINT_SELECTORS);
    const hintText = findLikelyCandidateName(collectText(hintElement));
    if (hintText) {
      return shared.shortText(hintText, 80);
    }

    const lines = shared.normalizeText(pageText).split("\n");
    const firstLine = lines.find((line) => line && line.length <= 40) || lines[0] || "";
    const firstLineName = findLikelyCandidateName(firstLine);
    return firstLineName ? shared.shortText(firstLineName, 80) : "";
  }

  function tokenizeSelectionText(text) {
    return shared.normalizeText(text)
      .split("\n")
      .map(function (line) { return shared.normalizeText(line); })
      .filter(function (line) {
        return line
          && line.length >= 4
          && line.length <= 40
          && !/^(收藏|不合适|举报|转发牛人|打招呼|经历概览|最近关注|期望|测试工程师|\d+岁|\d+年|本科|硕士|博士|大专|专科)$/.test(line)
          && !/^\d{4}([.-]\d{2})?/.test(line);
      })
      .slice(0, 12);
  }

  function hasRecommendDetailOverlay(doc) {
    const dialogRoot = firstMatch(doc, [
      ".dialog-wrap.active",
      ".boss-popup__wrapper.recommendV2"
    ]);
    if (!dialogRoot) {
      return false;
    }
    return Boolean(firstMatch(doc, [
      ".resume-right-side",
      ".resume-summary"
    ]));
  }

  function nowMs() {
    return Date.now();
  }

  function getPendingSelection(doc) {
    const pending = root.__BOSS_RESUME_SCORE_PENDING_SELECTION__;
    if (!pending) {
      return null;
    }
    if (nowMs() - Number(pending.observedAt || 0) > PENDING_SELECTION_TTL_MS) {
      root.__BOSS_RESUME_SCORE_PENDING_SELECTION__ = null;
      return null;
    }
    if (doc && pending.geekId) {
      const candidate = firstMatch(doc, ['.card-inner[data-geekid="' + pending.geekId + '"]']);
      if (candidate) {
        return Object.assign({}, pending, { element: candidate });
      }
    }
    return pending;
  }

  function currentSelectionEpoch() {
    return Number(root.__BOSS_RESUME_SCORE_SELECTION_EPOCH__ || 0);
  }

  function nearestCandidateCard(node) {
    let current = node;
    while (current && current !== root.document && current !== root.document.body) {
      if (current.classList && (current.classList.contains("candidate-card-wrap") || current.classList.contains("card-inner"))) {
        return current.classList.contains("card-inner") ? current : (current.querySelector ? current.querySelector(".card-inner") || current : current);
      }
      current = current.parentElement;
    }
    return null;
  }

  function extractCardSnapshot(card) {
    if (!card) {
      return null;
    }
    const nameNode = firstMatch(card, [".name", ".name-label", "img[alt]"]);
    let candidateName = "";
    if (nameNode && nameNode.tagName === "IMG" && typeof nameNode.getAttribute === "function") {
      candidateName = findLikelyCandidateName(nameNode.getAttribute("alt") || "");
    } else {
      candidateName = findLikelyCandidateName(collectText(nameNode));
    }
    return {
      geekId: typeof card.getAttribute === "function" ? (card.getAttribute("data-geekid") || card.getAttribute("data-geek") || "") : "",
      candidateName,
      cardText: collectText(card),
      observedAt: nowMs(),
      selectionEpoch: currentSelectionEpoch()
    };
  }

  function recordPendingSelection(card) {
    if (!card) {
      return;
    }
    const nextEpoch = currentSelectionEpoch() + 1;
    root.__BOSS_RESUME_SCORE_SELECTION_EPOCH__ = nextEpoch;
    const snapshot = extractCardSnapshot(card);
    if (!snapshot) {
      return;
    }
    root.__BOSS_RESUME_SCORE_PENDING_SELECTION__ = Object.assign({}, snapshot, {
      selectionEpoch: nextEpoch,
      observedAt: nowMs()
    });
  }

  function extractRecommendSelectionContext(doc, loc, meta) {
    const pageUrl = String((loc && loc.href) || "");
    if (!pageUrl.includes("/web/frame/recommend/")) {
      return null;
    }
    if (!hasRecommendDetailOverlay(doc)) {
      return null;
    }
    const summaryRoot = firstMatch(doc, [".resume-summary", ".resume-item-detail", ".resume-right-side"]);
    const summaryText = collectText(summaryRoot);
    const cards = queryAll(doc, ".candidate-card-wrap");
    if (!summaryText || !cards.length) {
      return null;
    }
    const tokens = tokenizeSelectionText(summaryText);
    const pendingSelection = getPendingSelection(doc);
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
      let score = hits.length * 240 + visibilityScore(card, doc);
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
          card,
          cardText,
          hits,
          candidateName: snapshot.candidateName || "",
          geekId: snapshot.geekId || ""
        };
        bestScore = score;
      }
    }
    if (!best || bestScore < 240) {
      return null;
    }
    const candidateName = best.candidateName || extractCandidateName(doc, best.cardText, best.card);
    const pageTitle = shared.normalizeText((doc && doc.title) || "");
    const includeSummary = best.hits && best.hits.length > 0;
    const pageText = shared.normalizeText([
      candidateName,
      best.cardText,
      includeSummary ? "经历概览" : "",
      includeSummary ? summaryText : ""
    ].filter(Boolean).join("\n"));
    const candidateHint = deriveCandidateHint(doc, pageText, best.card, candidateName);
    return {
      ok: true,
      isDetail: true,
      pageUrl,
      pageTitle,
      pageText,
      candidateName,
      candidateHint,
      geekId: best.geekId || "",
      visibilityScore: visibilityScore(best.card, doc) + visibilityScore(summaryRoot, doc),
      observedAt: nowMs(),
      selectionEpoch: pendingSelection ? Number(pendingSelection.selectionEpoch || 0) : currentSelectionEpoch(),
      contextKey: shared.buildCandidateKey({
        pageUrl,
        pageTitle,
        pageText,
        candidateName,
        candidateHint
      }),
      frameId: meta && typeof meta.frameId === "number" ? meta.frameId : 0
    };
  }

  function findDetailRoot(doc) {
    const roots = collectDetailRoots(doc);
    let bestRoot = null;
    let bestScore = Number.NEGATIVE_INFINITY;
    for (const candidate of roots) {
      const score = scoreDetailRoot(candidate, doc);
      if (score > bestScore) {
        bestRoot = candidate;
        bestScore = score;
      }
    }
    if (bestRoot) {
      return bestRoot;
    }
    if (doc && doc.body && isDetailText(collectText(doc.body))) {
      return doc.body;
    }
    return null;
  }

  function extractPageContext(doc, loc, meta) {
    const pageUrl = String((loc && loc.href) || "");
    const pageTitle = shared.normalizeText((doc && doc.title) || "");
    const recommendSelection = extractRecommendSelectionContext(doc, loc, meta);
    if (recommendSelection) {
      return recommendSelection;
    }
    if (pageUrl.includes("/web/frame/recommend/")) {
      return {
        ok: false,
        isDetail: false,
        reason: "candidate_detail_not_found",
        pageUrl,
        pageTitle,
        frameId: meta && typeof meta.frameId === "number" ? meta.frameId : 0
      };
    }
    const detailRoot = findDetailRoot(doc);
    if (!detailRoot || isSimilarSectionActive(doc)) {
      return {
        ok: false,
        isDetail: false,
        reason: "candidate_detail_not_found",
        pageUrl,
        pageTitle,
        frameId: meta && typeof meta.frameId === "number" ? meta.frameId : 0
      };
    }

    const pageText = collectText(detailRoot);
    const candidateName = extractCandidateName(doc, pageText, detailRoot);
    const candidateHint = deriveCandidateHint(doc, pageText, detailRoot, candidateName);
    const detailVisibilityScore = visibilityScore(detailRoot, doc);
    return {
      ok: true,
      isDetail: true,
      pageUrl,
      pageTitle,
      pageText,
      candidateName,
      candidateHint,
      geekId: "",
      visibilityScore: detailVisibilityScore,
      observedAt: nowMs(),
      selectionEpoch: currentSelectionEpoch(),
      contextKey: shared.buildCandidateKey({
        pageUrl,
        pageTitle,
        pageText,
        candidateName,
        candidateHint
      }),
      frameId: meta && typeof meta.frameId === "number" ? meta.frameId : 0
    };
  }

  function pageUrlFromDoc(doc) {
    return String(
      (doc && doc.location && doc.location.href)
      || (root && root.location && root.location.href)
      || ""
    );
  }

  function isRecommendDoc(doc) {
    return pageUrlFromDoc(doc).includes("/web/frame/recommend/");
  }

  function findRecommendBadgeMountRoot(doc) {
    return firstMatch(doc, [".resume-right-side", ".resume-simple-box", ".resume-item-detail", ".boss-popup__content"]);
  }

  function resolveBadgeMountRoot(doc, detailRoot) {
    if (isRecommendDoc(doc)) {
      return findRecommendBadgeMountRoot(doc) || detailRoot;
    }
    return detailRoot;
  }

  function applyBadgeStyle(badge, tone, compactMode) {
    const baseTone = tone === "score"
      ? ["background: linear-gradient(135deg, rgba(4,121,255,.12), rgba(0,190,189,.12))", "border: 1px solid rgba(4,121,255,.22)"]
      : ["background: linear-gradient(135deg, rgba(12,138,77,.10), rgba(15,111,255,.08))", "border: 1px solid rgba(12,138,77,.18)"];
    badge.style.cssText = [
      "margin: 0 0 12px 0",
      compactMode ? "padding: 10px 12px" : "padding: 10px 12px",
      compactMode ? "border-radius: 14px" : "border-radius: 12px",
      "font-family: -apple-system, BlinkMacSystemFont, sans-serif",
      compactMode ? "font-size: 12px" : "font-size: 13px",
      compactMode ? "line-height: 1.45" : "line-height: 1.5",
      "color: #17324d",
      "display: block",
      "width: 100%",
      "max-width: 100%",
      "box-sizing: border-box",
      "align-self: stretch",
      compactMode ? "box-shadow: 0 10px 24px rgba(23,50,77,.08)" : "",
      baseTone[0],
      baseTone[1]
    ].filter(Boolean).join(";");
  }

  function ensureBadge(doc, detailRoot) {
    const mountRoot = resolveBadgeMountRoot(doc, detailRoot);
    if (!doc || !mountRoot || typeof mountRoot.prepend !== "function") {
      return null;
    }
    let badge = doc.getElementById ? doc.getElementById(BADGE_ID) : null;
    if (!badge) {
      badge = doc.createElement("div");
      badge.id = BADGE_ID;
    }
    if (badge.parentElement !== mountRoot) {
      mountRoot.prepend(badge);
    }
    applyBadgeStyle(badge, "score", isRecommendDoc(doc));
    return badge;
  }

  function ensureQuickFitBadge(doc, detailRoot) {
    const mountRoot = resolveBadgeMountRoot(doc, detailRoot);
    if (!doc || !mountRoot || typeof mountRoot.prepend !== "function") {
      return null;
    }
    let badge = doc.getElementById ? doc.getElementById(QUICK_BADGE_ID) : null;
    if (!badge) {
      badge = doc.createElement("div");
      badge.id = QUICK_BADGE_ID;
    }
    if (badge.parentElement !== mountRoot) {
      mountRoot.prepend(badge);
    }
    applyBadgeStyle(badge, "quick", isRecommendDoc(doc));
    return badge;
  }

  function renderScoreBadge(doc, payload) {
    if (isRecommendDoc(doc)) {
      clearScoreBadge(doc);
      return { ok: false, reason: "candidate_detail_not_found" };
    }
    const detailRoot = findDetailRoot(doc);
    if (!detailRoot || isSimilarSectionActive(doc)) {
      return { ok: false, reason: "candidate_detail_not_found" };
    }
    const badge = ensureBadge(doc, detailRoot);
    if (!badge) {
      return { ok: false, reason: "badge_mount_failed" };
    }
    const tone = shared.decisionTone(payload && payload.decision);
    const compactMode = isRecommendDoc(doc);
    const toneColor = tone === "good" ? "#0c8a4d" : tone === "warn" ? "#a66300" : tone === "bad" ? "#b42318" : "#475467";
    const reason = (payload && payload.review_reasons && payload.review_reasons[0]) || (payload && payload.hard_filter_fail_reasons && payload.hard_filter_fail_reasons[0]) || "";
    badge.innerHTML = [
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">',
      '<div><strong style="font-size:14px;">系统评分</strong><div style="opacity:.72;">本地筛选后端</div></div>',
      '<div style="text-align:right;">',
      '<div style="font-size:22px;font-weight:700;">' + String(payload && payload.score !== undefined ? payload.score : "-") + "</div>",
      '<div style="color:' + toneColor + ';font-weight:600;">' + shared.localizeDecision((payload && payload.decision) || "pending") + "</div>",
      "</div>",
      "</div>",
      reason ? '<div style="margin-top:8px;opacity:.84;">' + shared.shortText(reason, compactMode ? 56 : 120) + "</div>" : "",
      payload && payload.fallback_used ? '<div style="margin-top:6px;color:#a66300;">已降级为启发式打分</div>' : ""
    ].join("");
    return { ok: true };
  }

  function renderQuickFitBadge(doc, payload) {
    if (isRecommendDoc(doc)) {
      clearQuickFitBadge(doc);
      return { ok: false, reason: "candidate_detail_not_found" };
    }
    const detailRoot = findDetailRoot(doc);
    if (!detailRoot || isSimilarSectionActive(doc)) {
      return { ok: false, reason: "candidate_detail_not_found" };
    }
    const badge = ensureQuickFitBadge(doc, detailRoot);
    if (!badge) {
      return { ok: false, reason: "badge_mount_failed" };
    }
    const compactMode = isRecommendDoc(doc);
    const matched = ((payload && payload.matched) || []).slice(0, compactMode ? 2 : 3);
    const evidenceLines = ((payload && payload.evidenceLines) || []).slice(0, compactMode ? 1 : 2);
    badge.innerHTML = [
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">',
      '<div><strong style="font-size:14px;">JD 速览</strong><div style="opacity:.72;">本地秒级规则</div></div>',
      "</div>",
      payload && payload.summary ? '<div style="margin-top:8px;opacity:.84;">' + shared.shortText(payload.summary, compactMode ? 48 : 120) + "</div>" : "",
      matched.length ? '<div style="margin-top:8px;">' + matched.map(function (entry) {
        return '<span style="display:inline-flex;margin:0 6px 6px 0;padding:4px 8px;border-radius:999px;background:rgba(15,111,255,.08);font-size:12px;">' + entry + "</span>";
      }).join("") + "</div>" : "",
      evidenceLines.length ? '<div style="margin-top:6px;opacity:.78;">' + evidenceLines.map(function (entry) {
        return "• " + entry;
      }).join("<br>") + "</div>" : ""
    ].join("");
    return { ok: true };
  }

  function clearScoreBadge(doc) {
    if (!doc || typeof doc.getElementById !== "function") {
      return { ok: false };
    }
    const badge = doc.getElementById(BADGE_ID);
    if (badge && typeof badge.remove === "function") {
      badge.remove();
    }
    return { ok: true };
  }

  function clearQuickFitBadge(doc) {
    if (!doc || typeof doc.getElementById !== "function") {
      return { ok: false };
    }
    const badge = doc.getElementById(QUICK_BADGE_ID);
    if (badge && typeof badge.remove === "function") {
      badge.remove();
    }
    return { ok: true };
  }

  function contextSignalSignature(payload) {
    if (!payload) {
      return "none";
    }
    if (payload.isDetail) {
      return "detail:" + String(payload.contextKey || "");
    }
    return "empty:" + String(payload.reason || "");
  }

  function emitContextSignal(chromeApi) {
    if (!chromeApi || !chromeApi.runtime || typeof chromeApi.runtime.sendMessage !== "function") {
      return;
    }
    const payload = extractPageContext(root.document, root.location, { frameId: 0 });
    if (!payload.isDetail && isRecommendDoc(root.document)) {
      clearScoreBadge(root.document);
      clearQuickFitBadge(root.document);
    }
    const signature = contextSignalSignature(payload);
    if (root.__BOSS_RESUME_SCORE_LAST_SIGNAL__ === signature) {
      return;
    }
    root.__BOSS_RESUME_SCORE_LAST_SIGNAL__ = signature;
    try {
      chromeApi.runtime.sendMessage({
        type: "boss_resume_score:page-context-signal",
        payload: payload
      });
    } catch (error) {
      // Ignore transient runtime messaging failures.
    }
  }

  function scheduleContextSignal(chromeApi) {
    if (root.__BOSS_RESUME_SCORE_SIGNAL_TIMER__) {
      root.clearTimeout(root.__BOSS_RESUME_SCORE_SIGNAL_TIMER__);
    }
    root.__BOSS_RESUME_SCORE_SIGNAL_TIMER__ = root.setTimeout(function () {
      root.__BOSS_RESUME_SCORE_SIGNAL_TIMER__ = null;
      emitContextSignal(chromeApi);
    }, CONTEXT_SIGNAL_DELAY_MS);
  }

  function observeContextChanges(chromeApi) {
    if (root.__BOSS_RESUME_SCORE_OBSERVER_READY__) {
      return;
    }
    root.__BOSS_RESUME_SCORE_OBSERVER_READY__ = true;
    const target = (root.document && (root.document.body || root.document.documentElement)) || null;
    if (target && typeof root.MutationObserver === "function") {
      const observer = new root.MutationObserver(function () {
        scheduleContextSignal(chromeApi);
      });
      observer.observe(target, {
        childList: true,
        subtree: true,
        characterData: true
      });
      root.__BOSS_RESUME_SCORE_OBSERVER__ = observer;
    }
    if (typeof root.addEventListener === "function") {
      root.addEventListener("click", function (event) {
        const card = nearestCandidateCard(event && event.target);
        if (!card) {
          return;
        }
        recordPendingSelection(card);
        scheduleContextSignal(chromeApi);
        root.setTimeout(function () { scheduleContextSignal(chromeApi); }, 220);
        root.setTimeout(function () { scheduleContextSignal(chromeApi); }, 560);
      }, true);
      root.addEventListener("scroll", function () {
        scheduleContextSignal(chromeApi);
      }, { passive: true });
      root.addEventListener("load", function () {
        scheduleContextSignal(chromeApi);
      });
    }
    scheduleContextSignal(chromeApi);
  }

  function register(chromeApi) {
    if (root.__BOSS_RESUME_SCORE_REGISTERED__) {
      return;
    }
    root.__BOSS_RESUME_SCORE_REGISTERED__ = true;
    chromeApi.runtime.onMessage.addListener(function (message, sender, sendResponse) {
      if (!message || !message.type) {
        return undefined;
      }
      if (message.type === "boss_resume_score:get-page-context") {
        sendResponse(extractPageContext(root.document, root.location, { frameId: sender && sender.frameId }));
        return false;
      }
      if (message.type === "boss_resume_score:show-score") {
        sendResponse(renderScoreBadge(root.document, message.payload || {}));
        return false;
      }
      if (message.type === "boss_resume_score:show-quick-fit") {
        sendResponse(renderQuickFitBadge(root.document, message.payload || {}));
        return false;
      }
      if (message.type === "boss_resume_score:clear-score") {
        sendResponse(clearScoreBadge(root.document));
        return false;
      }
      if (message.type === "boss_resume_score:clear-quick-fit") {
        sendResponse(clearQuickFitBadge(root.document));
        return false;
      }
      return undefined;
    });
    observeContextChanges(chromeApi);
  }

  return {
    extractPageContext,
    renderQuickFitBadge,
    renderScoreBadge,
    clearQuickFitBadge,
    clearScoreBadge,
    register
  };
});
