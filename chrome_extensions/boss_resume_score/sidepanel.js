(function (root, shared) {
  const POLL_INTERVAL_MS = 600;
  const BURST_REFRESH_DELAYS_MS = [120, 320];
  const PREFS_KEY = shared.PREFS_STORAGE_KEY || "boss_resume_score_prefs";
  const state = {
    currentContext: null,
    currentTarget: null,
    lastAutoKey: "",
    lastQuickKey: "",
    pollHandle: null,
    burstHandles: [],
    messageRefreshHandle: null,
    scoreRequestSeq: 0,
    trackingDraft: {
      candidateId: "",
      dirty: false,
      signature: ""
    },
    prefs: {
      jobId: "qa_test_engineer_v1",
      autoRescore: false,
      backendBaseUrl: shared.DEFAULT_BACKEND_BASE_URL || "http://127.0.0.1:8080"
    }
  };

  function runtimeSend(message) {
    return new Promise(function (resolve, reject) {
      chrome.runtime.sendMessage(message, function (response) {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(response || {});
      });
    });
  }

  function storageGet(area, key) {
    return new Promise(function (resolve) {
      area.get(key, function (payload) {
        resolve(payload ? payload[key] : undefined);
      });
    });
  }

  function storageSet(area, value) {
    return new Promise(function (resolve) {
      area.set(value, resolve);
    });
  }

  function clearBurstRefreshes() {
    while (state.burstHandles.length) {
      const handle = state.burstHandles.pop();
      root.clearTimeout(handle);
    }
  }

  function scheduleBurstRefreshes() {
    clearBurstRefreshes();
    BURST_REFRESH_DELAYS_MS.forEach(function (delay) {
      const handle = root.setTimeout(function () {
        refreshContext().catch(function () {});
      }, delay);
      state.burstHandles.push(handle);
    });
  }

  function scheduleMessageRefresh(delay) {
    if (state.messageRefreshHandle) {
      root.clearTimeout(state.messageRefreshHandle);
    }
    state.messageRefreshHandle = root.setTimeout(function () {
      state.messageRefreshHandle = null;
      refreshContext().catch(function () {});
    }, Math.max(0, Number(delay) || 0));
  }

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(message, tone) {
    const node = $("statusText");
    node.textContent = message;
    node.className = "status " + (tone || "neutral");
  }

  function renderJobs(items) {
    const select = $("jobSelect");
    select.innerHTML = "";
    (items || []).forEach(function (item) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = shared.localizeJobName(item.id, item.name);
      option.selected = item.id === state.prefs.jobId;
      select.appendChild(option);
    });
  }

  async function refreshJobs() {
    const jobsPayload = await runtimeSend({ type: "boss_resume_score:get-jobs" });
    renderJobs((jobsPayload && jobsPayload.items) || shared.JOB_OPTIONS_FALLBACK);
    $("jobSelect").value = state.prefs.jobId;
  }

  function renderStageOptions() {
    $("stageSelect").innerHTML = (shared.PIPELINE_STAGE_OPTIONS || []).map(function (stage) {
      return '<option value="' + stage + '">' + shared.localizeStage(stage) + "</option>";
    }).join("");
  }

  function renderContext(payload) {
    const context = payload && payload.context;
    if (!context) {
      $("candidateText").textContent = "-";
      $("pageText").textContent = "-";
      return;
    }
    const safeName = shared.extractCandidateNameFragment(context.candidateName || context.candidateHint || "");
    $("candidateText").textContent = safeName || "-";
    $("pageText").textContent = context.pageUrl || "-";
  }

  function trackingSignature(candidateId, pipelineState) {
    return [
      String(candidateId || ""),
      String((pipelineState && pipelineState.current_stage) || "new"),
      String((pipelineState && pipelineState.last_contact_result) || ""),
      String((pipelineState && pipelineState.next_follow_up_at) || ""),
      String((pipelineState && pipelineState.reason_notes) || "")
    ].join("|");
  }

  function setTrackingDraft(candidateId, pipelineState) {
    $("stageSelect").value = String((pipelineState && pipelineState.current_stage) || "new");
    $("contactResultInput").value = pipelineState && pipelineState.last_contact_result ? pipelineState.last_contact_result : "";
    $("followUpInput").value = pipelineState && pipelineState.next_follow_up_at ? pipelineState.next_follow_up_at : "";
    $("stageNotesInput").value = pipelineState && pipelineState.reason_notes ? pipelineState.reason_notes : "";
    state.trackingDraft = {
      candidateId: String(candidateId || ""),
      dirty: false,
      signature: trackingSignature(candidateId, pipelineState)
    };
  }

  function markTrackingDirty() {
    if (!state.currentContext || !state.currentContext.candidateId) {
      return;
    }
    state.trackingDraft.candidateId = String(state.currentContext.candidateId || "");
    state.trackingDraft.dirty = true;
    $("trackingMeta").textContent = "有未保存的跟踪修改，点击“保存状态”后会同步到后台。";
  }

  function resetTracking(message) {
    $("trackingTitle").textContent = "等待入库";
    $("trackingPill").textContent = "未入库";
    $("trackingPill").className = "pill neutral";
    $("trackingMeta").textContent = message || "识别到稳定详情页后会自动入库，随后可直接保存跟踪状态。";
    $("candidateIdText").textContent = "-";
    setTrackingDraft("", null);
    $("saveStageButton").disabled = true;
  }

  function defaultReasonCodeForStage(stage) {
    if (stage === "to_contact") return "skills_match";
    if (stage === "talent_pool") return "reusable_pool";
    if (stage === "rejected") return "skills_gap";
    if (stage === "do_not_contact") return "do_not_contact";
    if (stage === "needs_followup") return "resume_incomplete";
    if (stage === "interview_invited") return "candidate_positive";
    return null;
  }

  function defaultFinalDecisionForStage(stage) {
    if (stage === "to_contact" || stage === "interview_invited" || stage === "interview_scheduled" || stage === "contacted" || stage === "awaiting_reply") {
      return "recommend";
    }
    if (stage === "talent_pool") {
      return "talent_pool";
    }
    if (stage === "rejected" || stage === "do_not_contact") {
      return "reject";
    }
    if (stage === "to_review" || stage === "needs_followup") {
      return "review";
    }
    return "pending";
  }

  function renderTrackingFromContext(context) {
    const candidateId = context && context.candidateId;
    const pipelineState = context && context.pipelineState;
    if (!candidateId) {
      resetTracking("当前候选人正在自动入库，请稍候。");
      return;
    }
    const currentStage = String((pipelineState && pipelineState.current_stage) || "new");
    $("trackingTitle").textContent = shared.localizeStage(currentStage);
    $("trackingPill").textContent = shared.localizeStage(currentStage);
    $("trackingPill").className = "pill " + (currentStage === "rejected" || currentStage === "do_not_contact" ? "bad" : currentStage === "to_review" || currentStage === "needs_followup" ? "warn" : "good");
    $("candidateIdText").textContent = candidateId;
    const signature = trackingSignature(candidateId, pipelineState);
    const candidateChanged = state.trackingDraft.candidateId !== String(candidateId || "");
    if (candidateChanged || !state.trackingDraft.dirty) {
      setTrackingDraft(candidateId, pipelineState);
    } else if (state.trackingDraft.signature !== signature) {
      $("trackingMeta").textContent = "后台状态已更新，你有未保存的本地修改，保存后会覆盖为新的跟踪状态。";
    }
    if (!state.trackingDraft.dirty) {
      $("trackingMeta").textContent = pipelineState && pipelineState.manual_stage_locked
        ? "当前状态已由 HR 手动接管，后续自动评分不会覆盖。"
        : "候选人已入库，后续评分和快照会继续自动补充。";
    }
    $("saveStageButton").disabled = false;
  }

  function resetQuickFit(message) {
    $("quickFitTitle").textContent = "等待识别";
    $("quickFitPill").textContent = "待识别";
    $("quickFitPill").className = "pill neutral";
    $("quickFitMeta").textContent = message || "本地秒级规则，不等待后端模型。";
    $("quickFitMatchList").innerHTML = "";
    $("quickFitGapList").innerHTML = "";
  }

  async function applyContextPayload(payload) {
    const previousKey = state.currentContext && state.currentContext.contextKey;
    if (!payload || !payload.context) {
      return;
    }
    if (state.currentContext) {
      const currentEpoch = Number(state.currentContext.selectionEpoch || 0);
      const incomingEpoch = Number(payload.context.selectionEpoch || 0);
      const currentObservedAt = Number(state.currentContext.observedAt || 0);
      const incomingObservedAt = Number(payload.context.observedAt || 0);
      if (incomingEpoch < currentEpoch) {
        return;
      }
      if (incomingEpoch === currentEpoch && incomingObservedAt && currentObservedAt && incomingObservedAt < currentObservedAt) {
        return;
      }
    }
    state.currentContext = payload.context;
    state.currentTarget = {
      tabId: payload.tabId,
      frameId: payload.frameId
    };
    renderContext(payload);
    if (payload.context.contextKey !== previousKey) {
      resetResult("候选人已切换，等待新的打分结果。");
      resetTracking("当前候选人正在自动入库，请稍候。");
      scheduleBurstRefreshes();
    }
    renderTrackingFromContext(payload.context);
    await syncQuickFitBadge();
    setStatus("已识别到 BOSS 候选人详情页", "good");
    if (state.prefs.autoRescore && payload.context.contextKey !== state.lastAutoKey) {
      state.lastAutoKey = payload.context.contextKey;
      await triggerScore(false);
    }
  }

  function renderQuickFit(analysis) {
    if (!analysis) {
      resetQuickFit();
      return;
    }
    $("quickFitTitle").textContent = analysis.label || "待识别";
    $("quickFitPill").textContent = analysis.label || "待识别";
    $("quickFitPill").className = "pill " + (analysis.tone || "neutral");
    $("quickFitMeta").textContent = analysis.summary || "本地秒级规则，不等待后端模型。";
    $("quickFitMatchList").innerHTML = (analysis.matched || []).length
      ? analysis.matched.slice(0, 4).map(function (entry) { return "<li>" + entry + "</li>"; }).join("")
      : "<li>暂未命中明显的 JD 证据。</li>";
    $("quickFitGapList").innerHTML = (analysis.missing || []).length
      ? analysis.missing.slice(0, 4).map(function (entry) { return "<li>" + entry + "</li>"; }).join("")
      : "<li>当前未识别出明显缺口。</li>";
  }

  async function syncQuickFitBadge() {
    if (!state.currentContext || !state.currentTarget) {
      resetQuickFit();
      return;
    }
    const analysis = shared.analyzeQuickFit(state.prefs.jobId, state.currentContext.pageText || "");
    renderQuickFit(analysis);
    const quickKey = state.prefs.jobId + ":" + String(state.currentContext.contextKey || "");
    if (state.lastQuickKey === quickKey) {
      return;
    }
    state.lastQuickKey = quickKey;
    try {
      await runtimeSend({
        type: "boss_resume_score:render-quick-fit",
        tabId: state.currentTarget.tabId,
        frameId: state.currentTarget.frameId,
        context: state.currentContext,
        jobId: state.prefs.jobId,
        analysis: analysis
      });
    } catch (error) {
      // The page-side quick badge is best-effort only.
    }
  }

  function resetResult(message) {
    $("scoreValue").textContent = "-";
    $("decisionPill").textContent = shared.localizeDecision("pending");
    $("decisionPill").className = "pill neutral";
    $("resultMeta").textContent = message || "暂时还没有打分结果。";
    $("reasonList").innerHTML = "";
    $("dimensionList").innerHTML = "";
  }

  function renderResult(payload, contextSnapshot) {
    if (!payload || !payload.ok) {
      resetResult(payload && payload.error ? shared.localizeError(payload.error) : "暂时还没有打分结果。");
      return;
    }

    const decisionTone = shared.decisionTone(payload.decision);
    const displayContext = contextSnapshot || state.currentContext;
    const extractedName = payload.extracted_fields && payload.extracted_fields.name;
    const displayName = shared.extractCandidateNameFragment(
      (displayContext && (displayContext.candidateName || displayContext.candidateHint))
      || extractedName
      || ""
    ) || "-";
    if (state.currentContext) {
      state.currentContext = Object.assign({}, state.currentContext, {
        candidateId: payload.candidate_id || state.currentContext.candidateId || "",
        pipelineState: payload.pipeline_state || state.currentContext.pipelineState || null
      });
      renderTrackingFromContext(state.currentContext);
    }
    $("candidateText").textContent = displayName;
    $("scoreValue").textContent = payload.score === undefined ? "-" : Number(payload.score).toFixed(1);
    $("decisionPill").textContent = shared.localizeDecision(payload.decision || "pending");
    $("decisionPill").className = "pill " + decisionTone;
    $("resultMeta").textContent = payload.fallback_used
      ? "模型抽取暂不可用，当前结果来自启发式降级打分。"
      : payload.cacheHit
        ? "结果已命中本次会话缓存。"
        : "结果来自本地筛选后端的最新计算。";

    const reasons = []
      .concat(payload.review_reasons || [])
      .concat(payload.hard_filter_fail_reasons || [])
      .slice(0, 4);
    $("reasonList").innerHTML = reasons.length
      ? reasons.map(function (entry) { return "<li>" + entry + "</li>"; }).join("")
      : "<li>当前没有额外阻塞原因。</li>";

    const dimensions = Object.entries(payload.dimension_scores || {});
    $("dimensionList").innerHTML = dimensions.length
      ? dimensions
          .sort(function (left, right) { return Number(right[1]) - Number(left[1]); })
          .map(function (entry) {
            return "<li><strong>" + shared.localizeDimension(entry[0]) + "</strong>: " + Number(entry[1]).toFixed(1) + "</li>";
          })
          .join("")
      : "<li>当前没有维度分明细。</li>";
  }

  async function loadPrefs() {
    const saved = await storageGet(chrome.storage.local, PREFS_KEY);
    if (saved && typeof saved === "object") {
      state.prefs = Object.assign({}, state.prefs, saved);
    }
    state.prefs.backendBaseUrl = shared.normalizeBackendBaseUrl(state.prefs.backendBaseUrl);
    $("backendUrlInput").value = state.prefs.backendBaseUrl;
    $("autoToggle").checked = Boolean(state.prefs.autoRescore);
  }

  async function savePrefs() {
    await storageSet(chrome.storage.local, { [PREFS_KEY]: state.prefs });
  }

  async function saveBackendUrl() {
    const normalized = shared.normalizeBackendBaseUrl($("backendUrlInput").value);
    if (!normalized) {
      setStatus("后端地址格式无效，请输入 http://IP:端口", "bad");
      return;
    }
    $("backendUrlInput").value = normalized;
    if (state.prefs.backendBaseUrl === normalized) {
      setStatus("后端地址未变化", "neutral");
      return;
    }
    state.prefs.backendBaseUrl = normalized;
    state.lastAutoKey = "";
    state.lastQuickKey = "";
    await savePrefs();
    setStatus("后端地址已保存，正在重新连接...", "neutral");
    try {
      await refreshJobs();
      await refreshContext();
      setStatus("已连接到筛选后端：" + normalized, "good");
    } catch (error) {
      setStatus(error.message || ("无法连接到后端：" + normalized), "bad");
    }
  }

  async function refreshContext() {
    try {
      const payload = await runtimeSend({
        type: "boss_resume_score:get-active-context",
        jobId: state.prefs.jobId
      });
      if (!payload.ok) {
        throw new Error(shared.localizeError(payload.error || "当前标签页暂时无法识别"));
      }
      await applyContextPayload(payload);
    } catch (error) {
      const previousTarget = state.currentTarget;
      state.currentContext = null;
      state.currentTarget = null;
      state.lastAutoKey = "";
      state.lastQuickKey = "";
      clearBurstRefreshes();
      if (state.messageRefreshHandle) {
        root.clearTimeout(state.messageRefreshHandle);
        state.messageRefreshHandle = null;
      }
      renderContext(null);
      resetTracking("当前区域不是候选人详情，已暂停入库与跟踪。");
      resetQuickFit("当前区域不是候选人详情，已暂停 JD 速览。");
      resetResult("当前区域不是候选人详情，已暂停打分。");
      if (previousTarget) {
        runtimeSend({
          type: "boss_resume_score:clear-quick-fit",
          tabId: previousTarget.tabId,
          frameId: previousTarget.frameId
        }).catch(function () {});
      }
      setStatus(error.message || "请先在 BOSS 中打开候选人详情页。", "neutral");
    }
  }

  async function triggerScore(force) {
    if (!state.currentContext) {
      setStatus("请先打开候选人详情页，再执行打分。", "warn");
      return;
    }
    const requestContext = Object.assign({}, state.currentContext);
    const requestSeq = state.scoreRequestSeq + 1;
    state.scoreRequestSeq = requestSeq;
    setStatus(force ? "正在重新计算分数..." : "正在为当前候选人打分...", "neutral");
    try {
      const payload = await runtimeSend({
        type: "boss_resume_score:score-active-context",
        jobId: state.prefs.jobId,
        force: Boolean(force),
        context: requestContext,
        tabId: state.currentTarget && state.currentTarget.tabId,
        frameId: state.currentTarget && state.currentTarget.frameId
      });
      if (requestSeq !== state.scoreRequestSeq) {
        return;
      }
      if (!state.currentContext || state.currentContext.contextKey !== requestContext.contextKey) {
        return;
      }
      renderResult(payload, requestContext);
      if (!payload.ok) {
        throw new Error(shared.localizeError(payload.error || "打分失败"));
      }
      setStatus(payload.cacheHit ? "已展示缓存结果" : "打分结果已更新", payload.fallback_used ? "warn" : "good");
    } catch (error) {
      if (requestSeq !== state.scoreRequestSeq) {
        return;
      }
      if (!state.currentContext || state.currentContext.contextKey !== requestContext.contextKey) {
        return;
      }
      renderResult({ ok: false, error: error.message || "打分失败" }, requestContext);
      setStatus(error.message || "打分失败", "bad");
    }
  }

  async function syncCandidateNow(force) {
    if (!state.currentContext) {
      setStatus("请先打开候选人详情页，再执行入库。", "warn");
      return;
    }
    setStatus(force ? "正在刷新候选人入库状态..." : "正在同步候选人入库状态...", "neutral");
    try {
      const payload = await runtimeSend({
        type: "boss_resume_score:get-active-context",
        jobId: state.prefs.jobId,
        force: Boolean(force)
      });
      if (!payload.ok) {
        throw new Error(shared.localizeError(payload.error || "candidate_sync_failed"));
      }
      await applyContextPayload(payload);
      setStatus(payload.context && payload.context.candidateId ? "候选人已入库" : "候选人入库已更新", "good");
    } catch (error) {
      setStatus(error.message || "候选人入库失败", "bad");
    }
  }

  async function saveStage() {
    if (!state.currentContext || !state.currentContext.candidateId) {
      setStatus("当前候选人尚未完成入库，请稍候再试。", "warn");
      return;
    }
    const stage = $("stageSelect").value || "new";
    const payload = {
      operator: "boss_extension_hr",
      current_stage: stage,
      reason_code: defaultReasonCodeForStage(stage),
      reason_notes: $("stageNotesInput").value.trim() || null,
      final_decision: defaultFinalDecisionForStage(stage),
      last_contacted_at: (stage === "contacted" || stage === "awaiting_reply") ? new Date().toISOString().slice(0, 16) : null,
      last_contact_result: $("contactResultInput").value.trim() || null,
      next_follow_up_at: $("followUpInput").value || null,
      do_not_contact: stage === "do_not_contact",
      reusable_flag: stage === "talent_pool",
      talent_pool_status: stage === "talent_pool" ? "plugin_saved" : null
    };
    setStatus("正在保存跟踪状态...", "neutral");
    try {
      const result = await runtimeSend({
        type: "boss_resume_score:save-stage",
        candidateId: state.currentContext.candidateId,
        jobId: state.prefs.jobId,
        payload: payload,
        context: state.currentContext,
        tabId: state.currentTarget && state.currentTarget.tabId,
        frameId: state.currentTarget && state.currentTarget.frameId
      });
      if (!result.ok) {
        throw new Error(shared.localizeError(result.error || "candidate_stage_save_failed"));
      }
      state.trackingDraft.dirty = false;
      state.trackingDraft.signature = "";
      if (result.context) {
        await applyContextPayload({
          ok: true,
          tabId: result.tabId,
          frameId: result.frameId,
          context: result.context
        });
      }
      setStatus("跟踪状态已保存", "good");
    } catch (error) {
      setStatus(error.message || "保存跟踪状态失败", "bad");
    }
  }

  async function boot() {
    await loadPrefs();
    renderStageOptions();
    resetTracking();
    await refreshJobs();
    $("jobSelect").addEventListener("change", async function (event) {
      state.prefs.jobId = event.target.value;
      state.lastAutoKey = "";
      state.lastQuickKey = "";
      await savePrefs();
      await refreshContext();
    });
    $("autoToggle").addEventListener("change", async function (event) {
      state.prefs.autoRescore = Boolean(event.target.checked);
      state.lastAutoKey = "";
      state.lastQuickKey = "";
      await savePrefs();
      await refreshContext();
    });
    $("scoreButton").addEventListener("click", function () {
      triggerScore(false);
    });
    $("refreshButton").addEventListener("click", function () {
      triggerScore(true);
    });
    $("syncCandidateButton").addEventListener("click", function () {
      syncCandidateNow(true);
    });
    $("saveStageButton").addEventListener("click", function () {
      saveStage();
    });
    $("saveBackendButton").addEventListener("click", function () {
      saveBackendUrl();
    });
    $("backendUrlInput").addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        saveBackendUrl();
      }
    });
    $("stageSelect").addEventListener("change", markTrackingDirty);
    $("contactResultInput").addEventListener("input", markTrackingDirty);
    $("followUpInput").addEventListener("input", markTrackingDirty);
    $("stageNotesInput").addEventListener("input", markTrackingDirty);
    chrome.runtime.onMessage.addListener(function (message) {
      if (!message || message.type !== "boss_resume_score:page-context-updated") {
        return;
      }
      if (message.tabId === undefined) {
        scheduleMessageRefresh(60);
        return;
      }
      if (state.currentTarget && state.currentTarget.tabId !== message.tabId) {
        return;
      }
      if (message.context && message.context.isDetail) {
        applyContextPayload({
          ok: true,
          tabId: message.tabId,
          frameId: message.frameId || 0,
          context: message.context
        }).catch(function () {
          scheduleMessageRefresh(60);
        });
        return;
      }
      scheduleMessageRefresh(60);
    });

    await refreshContext();
    state.pollHandle = root.setInterval(refreshContext, POLL_INTERVAL_MS);
  }

  document.addEventListener("DOMContentLoaded", function () {
    boot().catch(function (error) {
      setStatus(error.message || "侧边栏初始化失败。", "bad");
    });
  });
})(window, window.BossResumeScoreShared);
