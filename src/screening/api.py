from __future__ import annotations

import json
import mimetypes
import os
import secrets
import shlex
import shutil
import time
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .boss_auth import reset_boss_storage_state, save_boss_storage_state, sync_boss_storage_state
from .db import init_db
from .extension_candidates import ExtensionCandidateIngestService
from .extension_scoring import ExtensionScoreService
from .hr_users import (
    create_hr_user,
    get_hr_user_by_id,
    get_hr_user_by_username,
    list_hr_users,
    record_hr_user_login,
    reset_hr_user_password,
    update_hr_user,
    verify_password,
)
from .jd_scorecard_repositories import (
    BUILTIN_ENGINE_TYPE,
    BUILTIN_SCORING_KIND,
    CUSTOM_ENGINE_TYPE,
    CUSTOM_SCORING_KIND,
    get_jd_scorecard,
    list_jd_scorecards,
    upsert_jd_scorecard,
)
from .models import ConfirmableAction, ReviewAction
from .orchestrator import ScreeningOrchestrator
from .phase2_imports import ResumeImportService
from .phase2_repositories import (
    get_resume_import_batch,
    list_resume_import_batches,
    list_resume_import_results,
)
from .phase2_scorecards import generate_scorecard_from_jd, normalize_phase2_scorecard
from .phase2_ui import phase2_page_html
from .pipeline_service import CollectionPipelineService
from .scorecards import normalize_builtin_scorecard
from .scoring_targets import get_scoring_target, list_scoring_targets
from .search_service import ResumeSearchService
from .repositories import (
    add_review_action,
    add_candidate_tag,
    add_candidate_timeline_event,
    create_task,
    get_candidate,
    get_candidate_workbench,
    get_collection_pipeline,
    get_candidate_pipeline_state,
    get_extension_candidate_binding,
    get_extension_candidate_binding_by_external_id,
    get_task,
    list_jobs,
    list_candidates_for_task,
    list_candidate_timeline,
    list_collection_pipeline_runs,
    list_hr_checklist_items,
    list_hr_workbench_items,
    list_logs_for_task,
    list_recent_tasks,
    save_candidate_follow_up,
    save_candidate_stage_action,
)


init_db()
SEARCH_SERVICE = ResumeSearchService()
ORCHESTRATOR = ScreeningOrchestrator(search_service=SEARCH_SERVICE)
PIPELINE_SERVICE = CollectionPipelineService(search_service=SEARCH_SERVICE)
ADMIN_FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "admin_frontend" / "dist"
ADMIN_FRONTEND_MANIFEST_PATH = ADMIN_FRONTEND_DIST_DIR / ".vite" / "manifest.json"
AUTH_COOKIE_NAME = "screening_session"
AUTH_USERNAME = os.getenv("SCREENING_WEB_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("SCREENING_WEB_PASSWORD", "admin")
AUTH_SESSION_MAX_AGE_SECONDS = max(600, int(os.getenv("SCREENING_WEB_SESSION_MAX_AGE_SECONDS", "43200")))
_AUTH_SESSIONS: dict[str, dict] = {}
WORKBENCH_STAGE_OPTIONS = [
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
    "do_not_contact",
]
WORKBENCH_REASON_CODES = [
    "skills_match",
    "skills_gap",
    "industry_fit",
    "industry_gap",
    "years_gap",
    "education_gap",
    "salary_gap",
    "city_gap",
    "resume_incomplete",
    "candidate_positive",
    "reusable_pool",
    "duplicate_candidate",
    "do_not_contact",
]
WORKBENCH_FINAL_DECISIONS = ["recommend", "review", "reject", "talent_pool", "pending"]


def _json(status: HTTPStatus, payload: dict) -> tuple[int, bytes]:
    return status.value, json.dumps(payload, ensure_ascii=True).encode("utf-8")


def _json_with_headers(status: HTTPStatus, payload: dict, headers: dict[str, str]) -> tuple[int, bytes, str, dict[str, str]]:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    return status.value, body, "application/json; charset=utf-8", headers


def _body(status: HTTPStatus, body: bytes, content_type: str, headers: dict[str, str] | None = None):
    if headers:
        return status.value, body, content_type, headers
    return status.value, body, content_type


def _html(status: HTTPStatus, html: str) -> tuple[int, bytes, str]:
    return _body(status, html.encode("utf-8"), "text/html; charset=utf-8")


def _load_admin_frontend_manifest() -> dict | None:
    try:
        if not ADMIN_FRONTEND_MANIFEST_PATH.exists():
            return None
        return json.loads(ADMIN_FRONTEND_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _admin_frontend_shell(
    *,
    title: str,
    page_key: str,
    fallback_heading: str,
    fallback_description: str,
    current_path: str,
    username: str | None = None,
    user_role: str | None = None,
    next_path: str | None = None,
) -> str | None:
    manifest = _load_admin_frontend_manifest()
    if not manifest:
        return None
    entry = manifest.get("index.html")
    if not isinstance(entry, dict):
        return None
    script_file = str(entry.get("file") or "").strip()
    css_files = [str(item).strip() for item in entry.get("css") or [] if str(item).strip()]
    if not script_file:
        return None
    bootstrap = {
        "currentPath": current_path,
        "pageKey": page_key,
        "pageTitle": title,
        "username": username,
        "userRole": user_role,
        "nextPath": next_path,
    }
    css_links = "\n".join(
        f'  <link rel="stylesheet" href="/admin-static/{quote(path)}" />' for path in css_files
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
{css_links}
</head>
<body>
  <div id="root">
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:32px;background:#f8fafc;color:#0f172a;font-family:'SF Pro Display','PingFang SC','Helvetica Neue',Arial,sans-serif;">
      <div style="width:min(100%,720px);padding:32px;border:1px solid #e2e8f0;border-radius:24px;background:rgba(255,255,255,.92);box-shadow:0 10px 30px rgba(15,23,42,.06);">
    <div style="font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#64748b;">HRClaw</div>
        <h1 style="margin:16px 0 0;font-size:32px;line-height:1.15;">{fallback_heading}</h1>
        <p style="margin:12px 0 0;font-size:15px;line-height:1.8;color:#475569;">{fallback_description}</p>
      </div>
    </div>
  </div>
  <script>
    window.__SCREENING_BOOTSTRAP__ = {json.dumps(bootstrap, ensure_ascii=False)};
  </script>
  <script type="module" src="/admin-static/{quote(script_file)}"></script>
</body>
</html>"""


def _admin_frontend_asset(path: str):
    relative = str(path or "").lstrip("/")
    target = (ADMIN_FRONTEND_DIST_DIR / relative).resolve()
    try:
        target.relative_to(ADMIN_FRONTEND_DIST_DIR.resolve())
    except Exception:
        return _json(HTTPStatus.NOT_FOUND, {"error": "Asset not found"})
    if not target.exists() or not target.is_file():
        return _json(HTTPStatus.NOT_FOUND, {"error": "Asset not found"})
    mime, _ = mimetypes.guess_type(str(target))
    return _body(HTTPStatus.OK, target.read_bytes(), mime or "application/octet-stream")


def _redirect(location: str, *, headers: dict[str, str] | None = None) -> tuple[int, bytes, str, dict[str, str]]:
    merged_headers = {"Location": location}
    if headers:
        merged_headers.update(headers)
    return _body(HTTPStatus.SEE_OTHER, b"", "text/plain; charset=utf-8", merged_headers)


def _header_get(handler, name: str, default: str = "") -> str:
    headers = getattr(handler, "headers", {})
    try:
        value = headers.get(name, default)
        return value if value is not None else default
    except Exception:
        return default


def _parse_cookies(handler) -> dict[str, str]:
    raw = _header_get(handler, "Cookie", "")
    if not raw:
        return {}
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        chunk = part.strip()
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _prune_sessions() -> None:
    now = int(time.time())
    expired = [token for token, meta in _AUTH_SESSIONS.items() if int(meta.get("expires_at", 0)) <= now]
    for token in expired:
        _AUTH_SESSIONS.pop(token, None)


def _current_session(handler) -> dict | None:
    _prune_sessions()
    token = _parse_cookies(handler).get(AUTH_COOKIE_NAME)
    if not token:
        return None
    session = _AUTH_SESSIONS.get(token)
    if not session:
        return None
    user_id = str(session.get("user_id") or "")
    if not user_id:
        return session
    user = get_hr_user_by_id(user_id)
    if not user or not bool(user.get("active")):
        _AUTH_SESSIONS.pop(token, None)
        return None
    session["username"] = str(user.get("username") or session.get("username") or "")
    session["display_name"] = str(user.get("display_name") or session.get("display_name") or session.get("username") or "")
    session["role"] = str(user.get("role") or session.get("role") or "hr")
    return session


def _current_user(handler) -> str | None:
    meta = _current_session(handler)
    if not meta:
        return None
    return str(meta.get("username") or "")


def _current_user_role(handler) -> str | None:
    meta = _current_session(handler)
    if not meta:
        return None
    return str(meta.get("role") or "")


def _current_user_id(handler) -> str | None:
    meta = _current_session(handler)
    if not meta:
        return None
    return str(meta.get("user_id") or "")


def _auth_cookie_value(token: str) -> str:
    return f"{AUTH_COOKIE_NAME}={token}; Path=/; HttpOnly; Max-Age={AUTH_SESSION_MAX_AGE_SECONDS}; SameSite=Lax"


def _clear_auth_cookie_value() -> str:
    return f"{AUTH_COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax"


def _require_page_auth(handler, *, path: str) -> tuple[int, bytes, str, dict[str, str]] | None:
    if path in {"/login"}:
        return None
    if not path.startswith("/hr/") and path != "/":
        return None
    if _current_user(handler):
        return None
    return _redirect(f"/login?next={quote(path)}")


def _require_admin_json(handler):
    if not _current_session(handler):
        return _json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"})
    if _current_user_role(handler) != "admin":
        return _json(HTTPStatus.FORBIDDEN, {"error": "仅管理员可执行该操作"})
    return None


def _force_model_env() -> None:
    os.environ["SCREENING_BROWSER_AGENT"] = "playwright"
    os.environ["SCREENING_ENABLE_MODEL_EXTRACTION"] = "true"
    # Precision-first default policy: auto-release only for score >= 90.
    os.environ.setdefault("SCREENING_AUTO_GREET_THRESHOLD", "90")
    os.environ.setdefault("SCREENING_AUTO_GREET_ALLOW_NON_RECOMMEND", "0")
    provider = os.getenv("SCREENING_EXTRACTION_PROVIDER", "kimi_cli").strip().lower() or "kimi_cli"
    os.environ["SCREENING_EXTRACTION_PROVIDER"] = provider
    os.environ.setdefault("SCREENING_EXTRACTION_MODEL", "kimi-for-coding")
    if provider == "kimi_cli":
        os.environ.setdefault("SCREENING_EXTRACTION_MODEL", "kimi-for-coding")
        os.environ.setdefault("SCREENING_KIMI_CLI_COMMAND", "kimi")
        return

    # Non-CLI providers must be configured explicitly through SCREENING_LLM_* variables.
    os.environ.setdefault("SCREENING_LLM_BASE_URL", "")


def _model_precheck_error() -> str | None:
    provider = os.getenv("SCREENING_EXTRACTION_PROVIDER", "kimi_cli").strip().lower() or "kimi_cli"
    if provider == "kimi_cli":
        raw_command = os.getenv("SCREENING_KIMI_CLI_COMMAND", "").strip()
        if not raw_command:
            return "请先配置 SCREENING_KIMI_CLI_COMMAND（例如 kimi）"
        command_tokens = shlex.split(raw_command)
        if not command_tokens:
            return "SCREENING_KIMI_CLI_COMMAND 为空，请检查配置"
        command = command_tokens[0]
        if not (shutil.which(command) or Path(command).exists()):
            return f"Kimi CLI 命令不存在：{command}，请先安装并确保可执行"
        return None
    if not os.getenv("SCREENING_LLM_API_KEY"):
        return "请先配置 SCREENING_LLM_API_KEY（当前未使用硅基流动）"
    return None


def _read_json(handler) -> dict:
    length = int(_header_get(handler, "Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8"))


def _bool_query_param(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _login_page_html(next_path: str) -> str:
    safe_next = next_path if next_path.startswith("/") else "/hr/tasks"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>登录 - HRClaw</title>
  <style>
    :root {{
      --boss-blue: #00bebd;
      --boss-deep: #0479ff;
      --bg: #f5f8ff;
      --card: #ffffff;
      --text: #1f2937;
      --line: #dbe5f4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      background: radial-gradient(1000px 360px at 20% -10%, #d7fdfc 0%, transparent 70%),
                  radial-gradient(900px 300px at 100% 0%, #d8e9ff 0%, transparent 60%),
                  var(--bg);
      color: var(--text);
      display: grid;
      place-items: center;
      padding: 20px;
    }}
    .card {{
      width: 100%;
      max-width: 420px;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 16px 40px rgba(4, 121, 255, 0.12);
      overflow: hidden;
    }}
    .banner {{
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
      color: #fff;
      padding: 18px 20px;
      font-weight: 700;
      font-size: 18px;
      letter-spacing: .3px;
    }}
    .body {{ padding: 18px 20px 20px; }}
    label {{ display: block; margin: 8px 0 6px; font-size: 13px; color: #5b6476; }}
    input {{
      width: 100%;
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0 12px;
      outline: none;
      font-size: 14px;
    }}
    input:focus {{ border-color: var(--boss-deep); box-shadow: 0 0 0 3px rgba(4, 121, 255, 0.15); }}
    button {{
      margin-top: 14px;
      width: 100%;
      height: 42px;
      border: 0;
      border-radius: 10px;
      color: #fff;
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
      cursor: pointer;
      font-size: 15px;
      font-weight: 600;
    }}
    .hint {{ margin-top: 10px; color: #6b7280; font-size: 12px; }}
    .error {{ margin-top: 10px; color: #dc2626; font-size: 12px; min-height: 18px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="banner">HRClaw</div>
    <div class="body">
      <form id="loginForm">
        <label>用户名</label>
        <input id="username" value="admin" autocomplete="username" />
        <label>密码</label>
        <input id="password" type="password" value="admin" autocomplete="current-password" />
        <button type="submit">登录</button>
        <div class="hint">默认账号：admin / admin</div>
        <div id="error" class="error"></div>
      </form>
    </div>
  </div>
  <script>
    const form = document.getElementById("loginForm");
    const errEl = document.getElementById("error");
    form.addEventListener("submit", async (e) => {{
      e.preventDefault();
      errEl.textContent = "";
      const payload = {{
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value
      }};
      try {{
        const res = await fetch("/api/login", {{
          method: "POST",
          headers: {{"Content-Type":"application/json"}},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `登录失败(${{res.status}})`);
        window.location.href = "{safe_next}";
      }} catch (err) {{
        errEl.textContent = err.message || "登录失败";
      }}
    }});
  </script>
</body>
</html>"""


def _task_runner_page_html(username: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>HR任务执行 - Recommend流程</title>
  <style>
    :root {{
      --boss-blue: #00bebd;
      --boss-deep: #0479ff;
      --bg: #f4f8ff;
      --card: #fff;
      --line: #d9e3f3;
      --text: #162033;
      --muted: #5d6785;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: radial-gradient(1100px 360px at -10% -10%, #d8fffb 0%, transparent 60%),
                  radial-gradient(1200px 420px at 100% -20%, #dce8ff 0%, transparent 60%),
                  var(--bg);
    }}
    .top {{
      position: sticky; top: 0; z-index: 3;
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
      color: #fff;
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 18px;
    }}
    .brand {{ font-weight: 700; letter-spacing: .3px; }}
    .topNav {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .navGroup {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.12);
    }}
    .navLabel {{
      font-size: 12px;
      color: rgba(255,255,255,.78);
    }}
    .top a, .top button {{
      color: #fff; text-decoration: none; background: transparent; border: 1px solid rgba(255,255,255,.45);
      border-radius: 999px; padding: 6px 12px; cursor: pointer; font-size: 12px;
    }}
    .quickGrid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .quickCard {{
      display: block;
      text-decoration: none;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: linear-gradient(180deg, #ffffff, #f7fbff);
      box-shadow: 0 10px 22px rgba(4, 121, 255, 0.06);
    }}
    .quickCard strong {{
      display: block;
      font-size: 16px;
      margin-bottom: 6px;
      color: #1947be;
    }}
    .quickCard span {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .wrap {{ max-width: 1000px; margin: 22px auto; padding: 0 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 12px 30px rgba(4, 121, 255, 0.08);
    }}
    h1 {{ margin: 0 0 10px; font-size: 22px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .form {{
      margin-top: 12px;
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 10px;
    }}
    .field label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
    .field input, .field select {{
      width: 100%; height: 38px; border: 1px solid var(--line); border-radius: 10px; padding: 0 10px;
    }}
    .actions {{ margin-top: 12px; display: flex; flex-wrap: wrap; gap: 10px; }}
    .btn {{
      border: 0; border-radius: 10px; cursor: pointer; height: 38px; padding: 0 14px; color: #fff; font-weight: 600;
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
    }}
    .btn.secondary {{ background: #fff; color: #2156d9; border: 1px solid #bad1ff; }}
    pre {{
      margin: 0; white-space: pre-wrap; word-break: break-word; max-height: 360px; overflow: auto;
      background: #0f172a; color: #d4e2ff; border-radius: 10px; padding: 12px; font-size: 12px;
    }}
    @media (max-width: 860px) {{
      .form {{ grid-template-columns: 1fr 1fr; }}
      .quickGrid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="top">
    <div class="brand">HRClaw · Recommend流程</div>
    <div class="topNav">
      <span>用户：{username}</span>
      <div class="navGroup">
        <span class="navLabel">流程</span>
        <a href="/hr/workbench">推荐处理台</a>
        <a href="/hr/checklist">Checklist</a>
      </div>
      <div class="navGroup">
        <span class="navLabel">搜索</span>
        <a href="/hr/search">高级搜索</a>
        <a href="/hr/phase2">JD评分卡</a>
      </div>
      <button id="logoutBtn" type="button">退出</button>
    </div>
  </div>
  <div class="wrap">
    <div class="grid">
      <div class="card">
        <h1>创建并执行任务</h1>
        <div class="muted">执行顺序已固定：HR 先在已安装插件的 Chrome 中手动登录 BOSS，插件同步当前会话，系统确认后再执行 recommend 筛选与打分。</div>
        <div class="form">
          <div class="field">
            <label>岗位</label>
            <select id="jobId"></select>
          </div>
          <div class="field">
            <label>最大人数</label>
            <input id="maxCandidates" type="number" min="1" max="200" value="50" />
          </div>
          <div class="field">
            <label>最大分页</label>
            <input id="maxPages" type="number" min="1" max="100" value="30" />
          </div>
          <div class="field">
            <label>排序</label>
            <select id="sortBy">
              <option value="active">活跃优先</option>
              <option value="recent">最新优先</option>
            </select>
          </div>
        </div>
        <div class="actions">
          <button id="resetSessionBtn" class="btn secondary" type="button">清空已保存会话</button>
          <button id="saveSessionBtn" class="btn secondary" type="button">检查已同步的BOSS会话</button>
          <button id="runBtn" class="btn" type="button">创建并执行Recommend任务</button>
        </div>
      </div>
      <div class="card">
        <h1>独立入口</h1>
        <div class="muted">高级搜索和 Checklist 已拆成两个独立模块，入口分开显示，避免混淆。</div>
        <div class="quickGrid" style="margin-top:12px;">
          <a class="quickCard" href="/hr/workbench">
            <strong>推荐处理台</strong>
            <span>集中处理推荐牛人结果，保存阶段、原因码、标签和跟进计划。</span>
          </a>
          <a class="quickCard" href="/hr/checklist">
            <strong>Checklist</strong>
            <span>查看任务清单、评分结果、复核状态和证据明细。</span>
          </a>
          <a class="quickCard" href="/hr/search">
            <strong>高级搜索</strong>
            <span>基于 JD 或自然语言需求，从本地简历库直接检索候选人。</span>
          </a>
          <a class="quickCard" href="/hr/phase2">
            <strong>JD评分卡</strong>
            <span>根据 JD 生成评分卡，并批量导入 Word/PDF 简历做筛查与打分。</span>
          </a>
        </div>
      </div>
      <div class="card">
        <div class="muted">执行日志</div>
        <pre id="logBox">等待操作...</pre>
      </div>
    </div>
  </div>
  <script>
    const jobId = document.getElementById("jobId");
    const maxCandidates = document.getElementById("maxCandidates");
    const maxPages = document.getElementById("maxPages");
    const sortBy = document.getElementById("sortBy");
    const logBox = document.getElementById("logBox");
    const resetSessionBtn = document.getElementById("resetSessionBtn");
    const saveSessionBtn = document.getElementById("saveSessionBtn");
    const runBtn = document.getElementById("runBtn");
    const logoutBtn = document.getElementById("logoutBtn");

    function log(msg) {{
      const now = new Date().toLocaleString();
      logBox.textContent = `[${{now}}] ${{msg}}\\n` + logBox.textContent;
    }}

    async function api(path, payload) {{
      const res = await fetch(path, {{
        method: "POST",
        headers: {{"Content-Type":"application/json"}},
        body: JSON.stringify(payload || {{}})
      }});
      const data = await res.json().catch(() => ({{}}));
      if (!res.ok) throw new Error(data.error || `请求失败(${{res.status}})`);
      return data;
    }}

    async function loadJobs() {{
      const res = await fetch("/api/jobs");
      const data = await res.json();
      jobId.innerHTML = (data.items || []).map(item => `<option value="${{item.id}}">${{item.name}} (${{item.id}})</option>`).join("");
    }}

    async function resetSessionAndRelogin() {{
      resetSessionBtn.disabled = true;
      log("开始清空本地已保存的 BOSS 会话...");
      try {{
        const data = await api("/api/boss/session/reset", {{}});
        log(data.message || "已清空本地会话。请先在 Chrome 的 BOSS 页面手动登录，并刷新一次 BOSS 页面让插件重新同步。");
      }} catch (err) {{
        log(`清空旧会话失败：${{err.message}}`);
      }} finally {{
        resetSessionBtn.disabled = false;
      }}
    }}

    async function saveSessionOnly() {{
      saveSessionBtn.disabled = true;
      log("开始检查当前 Chrome 已同步的 BOSS 会话。如果你刚手动登录 BOSS，请先刷新一次 BOSS 页面，让插件完成同步。");
      try {{
        const data = await api("/api/boss/session/save", {{}});
        log(`会话检测通过并已保存：login_detected=${{data.login_detected}}, reason=${{data.reason}}`);
      }} catch (err) {{
        log(`会话保存失败：${{err.message}}`);
      }} finally {{
        saveSessionBtn.disabled = false;
      }}
    }}

    async function createAndRun() {{
      runBtn.disabled = true;
      log("开始创建并执行任务（流程：校验已保存会话 -> recommend筛选）...");
      try {{
        const payload = {{
          job_id: jobId.value,
          max_candidates: Number(maxCandidates.value || 50),
          max_pages: Number(maxPages.value || 30),
          sort_by: sortBy.value
        }};
        const data = await api("/api/recommend/run", payload);
        log(`任务完成：task_id=${{data.task_id}}, 处理=${{(data.result?.processed || []).length}}`);
        if (data.task_id) {{
          window.location.href = `/hr/checklist?task_id=${{encodeURIComponent(data.task_id)}}`;
        }}
      }} catch (err) {{
        log(`执行失败：${{err.message}}`);
      }} finally {{
        runBtn.disabled = false;
      }}
    }}

    resetSessionBtn.addEventListener("click", resetSessionAndRelogin);
    saveSessionBtn.addEventListener("click", saveSessionOnly);
    runBtn.addEventListener("click", createAndRun);
    logoutBtn.addEventListener("click", async () => {{
      try {{
        await api("/api/logout", {{}});
      }} catch (_) {{}}
      window.location.href = "/login";
    }});
    loadJobs().catch(err => log(`加载岗位失败：${{err.message}}`));
  </script>
</body>
</html>"""


def _search_page_html(username: str) -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>高级搜索 - 本地JD搜索引擎</title>
  <style>
    :root {
      --boss-primary: #18d2d1;
      --boss-primary-deep: #0f243e;
      --boss-accent: #7d75ff;
      --bg: linear-gradient(180deg, #dcd6ff 0%, #eef7ff 24%, #eef6ff 100%);
      --panel: rgba(255, 255, 255, 0.94);
      --line: #e8edf5;
      --soft: #f7f9fc;
      --text: #17233d;
      --muted: #7b8498;
      --good: #17c5c7;
      --warn: #ef9a48;
      --bad: #ee6b74;
      --shadow: 0 22px 54px rgba(76, 91, 140, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    .top {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 24px;
      backdrop-filter: blur(18px);
      background: rgba(255, 255, 255, 0.56);
      border-bottom: 1px solid rgba(255, 255, 255, 0.7);
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
      background: linear-gradient(145deg, #5a6cff, #20d0cf);
      box-shadow: 0 16px 30px rgba(73, 116, 255, 0.22);
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
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid rgba(209, 221, 241, 0.8);
    }
    .navLabel {
      font-size: 12px;
      color: var(--muted);
    }
    .top a,
    .top button {
      color: var(--text);
      text-decoration: none;
      background: #fff;
      border: 1px solid #d7e2f2;
      border-radius: 999px;
      padding: 7px 12px;
      cursor: pointer;
      font-size: 12px;
    }
    .top button:hover,
    .top a:hover {
      border-color: #a8c7ff;
      color: #2754c5;
    }
    .wrap {
      width: min(100%, 1880px);
      margin: 18px auto 0;
      padding: 0 16px 20px;
    }
    .searchShell {
      display: grid;
      grid-template-columns: 420px minmax(0, 1fr);
      gap: 18px;
      min-height: calc(100vh - 118px);
    }
    .leftPanel,
    .rightPanel {
      background: var(--panel);
      border: 1px solid rgba(255, 255, 255, 0.7);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }
    .leftPanel {
      display: flex;
      flex-direction: column;
      padding: 28px 24px 18px;
    }
    .panelTitle {
      margin: 0;
      font-size: 28px;
      line-height: 1.1;
      font-weight: 700;
    }
    .panelSub {
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    .roleSelect {
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;
      margin-top: 24px;
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid #dfe7f1;
      background: linear-gradient(180deg, #fff, #fbfdff);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
    }
    .roleSelect input {
      flex: 1;
      border: 0;
      outline: 0;
      background: transparent;
      padding: 0;
      font-size: 17px;
      color: #244282;
    }
    .caret {
      width: 14px;
      height: 14px;
      border-right: 2px solid #b6c1d6;
      border-bottom: 2px solid #b6c1d6;
      transform: rotate(45deg) translateY(-2px);
      flex: 0 0 auto;
    }
    .section {
      margin-top: 28px;
    }
    .sectionHead {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .sectionLabel {
      display: inline-flex;
      align-items: center;
      gap: 12px;
      font-size: 17px;
      font-weight: 700;
    }
    .sectionLabel::before {
      content: "";
      width: 6px;
      height: 28px;
      border-radius: 999px;
      background: linear-gradient(180deg, #7c71ff, #3fcde0);
      box-shadow: 0 6px 18px rgba(126, 116, 255, 0.35);
    }
    .addConditionBtn {
      border: 0;
      background: transparent;
      color: var(--good);
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      padding: 0;
    }
    .conditionList {
      display: grid;
      gap: 12px;
    }
    .conditionRow {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 34px;
      gap: 10px;
      align-items: center;
    }
    .conditionRow input {
      width: 100%;
      border: 1px solid #e1e7ef;
      border-radius: 16px;
      padding: 15px 18px;
      font-size: 17px;
      color: #223760;
      background: #fff;
      outline: 0;
    }
    .conditionRow input:focus,
    .roleSelect input:focus {
      box-shadow: 0 0 0 4px rgba(24, 210, 209, 0.12);
    }
    .trashBtn {
      border: 0;
      width: 34px;
      height: 34px;
      border-radius: 12px;
      background: #f4f7fb;
      color: #a8b2c8;
      font-size: 18px;
      cursor: pointer;
    }
    .leftFormFooter {
      margin-top: 26px;
      padding-top: 18px;
      border-top: 1px solid #edf2f8;
    }
    .miniGrid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .miniField {
      margin-bottom: 10px;
    }
    .miniField label {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .miniField input,
    .miniField select,
    .notesBox textarea {
      width: 100%;
      border: 1px solid #e1e7ef;
      border-radius: 14px;
      padding: 11px 14px;
      font-size: 14px;
      background: #fff;
      color: var(--text);
      outline: 0;
    }
    .notesBox {
      margin-top: 8px;
    }
    .notesBox textarea {
      min-height: 88px;
      resize: vertical;
    }
    .explainRow {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 16px;
      background: #f7fafc;
      color: var(--muted);
      font-size: 13px;
    }
    .switch {
      position: relative;
      width: 44px;
      height: 26px;
      flex: 0 0 auto;
    }
    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
      position: absolute;
    }
    .slider {
      position: absolute;
      inset: 0;
      border-radius: 999px;
      background: #d7dfeb;
      transition: .2s ease;
      cursor: pointer;
    }
    .slider::before {
      content: "";
      position: absolute;
      width: 20px;
      height: 20px;
      left: 3px;
      top: 3px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 2px 8px rgba(39, 65, 119, 0.2);
      transition: .2s ease;
    }
    .switch input:checked + .slider {
      background: linear-gradient(145deg, #60d4e9, #17c5c7);
    }
    .switch input:checked + .slider::before {
      transform: translateX(18px);
    }
    .metaBox {
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 18px;
      background: linear-gradient(180deg, #fafcff, #f4f8ff);
      border: 1px solid #e4ecf8;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .leftFooter {
      margin-top: auto;
      padding-top: 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .quota {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #3d5a9a;
      font-size: 15px;
    }
    .quotaSpark {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #fff 0%, #fbfbff 22%, #8d7bff 55%, #4dd3e2 100%);
      box-shadow: 0 8px 18px rgba(119, 110, 255, 0.22);
    }
    .footerActions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .ghostBtn,
    .primaryBtn {
      border-radius: 18px;
      height: 54px;
      padding: 0 24px;
      border: 0;
      cursor: pointer;
      font-size: 18px;
      font-weight: 700;
    }
    .ghostBtn {
      background: #eef4fb;
      color: #355ba0;
      border: 1px solid #dbe5f2;
    }
    .primaryBtn {
      color: #fff;
      min-width: 168px;
      background: linear-gradient(135deg, #131f4a, #102246 48%, #0ed2d2 180%);
      box-shadow: 0 16px 34px rgba(19, 31, 74, 0.28);
    }
    .rightPanel {
      padding: 20px 22px 0;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .resultsTop {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 6px 8px 16px;
      border-bottom: 1px solid #eef2f7;
    }
    .resultsTitle {
      font-size: 30px;
      font-weight: 700;
    }
    .resultsStatus {
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }
    .resultsStatus strong {
      color: var(--good);
      font-weight: 700;
    }
    .subscriptionBox {
      display: inline-flex;
      align-items: center;
      gap: 14px;
      padding: 14px 20px;
      border-radius: 18px;
      background: #f7f8fb;
      border: 1px solid #eef2f8;
      color: #223760;
      font-size: 16px;
      white-space: nowrap;
    }
    .resultsWrap {
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding-right: 6px;
    }
    .resultsWrap::-webkit-scrollbar {
      width: 10px;
    }
    .resultsWrap::-webkit-scrollbar-thumb {
      border-radius: 999px;
      background: #dfe5ef;
    }
    .resultsList {
      padding: 10px 0 20px;
    }
    .candidateCard {
      padding: 20px 8px 24px;
      border-bottom: 1px solid #edf2f7;
    }
    .candidateTopline {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
      color: var(--muted);
      font-size: 14px;
    }
    .candidateTopline strong {
      color: var(--good);
    }
    .candidateBadge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: #f4f7fb;
      color: #5e6d8d;
      border: 1px solid #e2e8f1;
    }
    .candidateBadge.recommend {
      color: #0e9f6e;
      background: rgba(23, 197, 199, 0.12);
      border-color: rgba(23, 197, 199, 0.2);
    }
    .candidateBadge.review {
      color: #5b67ff;
      background: rgba(125, 117, 255, 0.12);
      border-color: rgba(125, 117, 255, 0.18);
    }
    .candidateBadge.reject {
      color: #e26a73;
      background: rgba(238, 107, 116, 0.12);
      border-color: rgba(238, 107, 116, 0.2);
    }
    .candidateRow {
      display: grid;
      grid-template-columns: 84px minmax(0, 1fr) 150px;
      gap: 18px;
      align-items: start;
    }
    .avatar {
      width: 72px;
      height: 72px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      font-weight: 700;
      color: #fff;
      background: linear-gradient(135deg, #7d74ff, #4dd3e2);
      box-shadow: 0 16px 26px rgba(117, 107, 255, 0.2);
    }
    .candidateName {
      font-size: 28px;
      font-weight: 700;
      line-height: 1.1;
    }
    .metaLine {
      margin-top: 8px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: #293d65;
      font-size: 16px;
    }
    .dotSep {
      color: #bcc4d3;
    }
    .factRow {
      margin-top: 14px;
      display: grid;
      gap: 10px;
      color: #344669;
      font-size: 16px;
    }
    .factItem {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .factIcon {
      width: 18px;
      text-align: center;
      opacity: 0.6;
      flex: 0 0 auto;
    }
    .factText {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .reasonRow {
      margin-top: 18px;
      display: grid;
      grid-template-columns: 132px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }
    .reasonBadge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 84px;
      padding: 10px 14px;
      border-radius: 14px;
      background: linear-gradient(180deg, rgba(125, 117, 255, 0.16), rgba(125, 117, 255, 0.08));
      color: #6a62ff;
      font-size: 16px;
      font-weight: 700;
    }
    .reasonText {
      color: #3b4c70;
      font-size: 17px;
      line-height: 1.8;
      word-break: break-word;
    }
    .chipRow {
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .miniChip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 13px;
      background: #f6f8fc;
      color: #5f6f8f;
      border: 1px solid #e5ebf4;
    }
    .miniChip.risk {
      color: #d47b21;
      background: rgba(239, 154, 72, 0.12);
      border-color: rgba(239, 154, 72, 0.18);
    }
    .miniChip.ask {
      color: #4d63cf;
      background: rgba(125, 117, 255, 0.12);
      border-color: rgba(125, 117, 255, 0.18);
    }
    .candidateSide {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 14px;
    }
    .scorePill {
      display: inline-flex;
      align-items: baseline;
      gap: 4px;
      color: #132754;
      font-size: 16px;
      font-weight: 700;
    }
    .scorePill strong {
      font-size: 34px;
      color: #18367e;
      line-height: 1;
    }
    .actionBtn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 116px;
      height: 54px;
      padding: 0 18px;
      border-radius: 18px;
      border: 2px solid rgba(24, 210, 209, 0.55);
      color: #14bcbc;
      text-decoration: none;
      background: #fff;
      font-size: 16px;
      font-weight: 700;
    }
    .sideLinks {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 8px;
      width: 100%;
    }
    .textLink {
      color: #5470c8;
      text-decoration: none;
      font-size: 13px;
    }
    .emptyState {
      display: grid;
      place-items: center;
      min-height: 420px;
      color: var(--muted);
      font-size: 16px;
      text-align: center;
      padding: 20px;
    }
    @media (max-width: 1180px) {
      .searchShell {
        grid-template-columns: 1fr;
      }
      .leftPanel {
        min-height: auto;
      }
      .resultsWrap {
        max-height: none;
      }
    }
    @media (max-width: 860px) {
      .candidateRow,
      .reasonRow {
        grid-template-columns: 1fr;
      }
      .candidateSide {
        align-items: flex-start;
      }
      .sideLinks {
        align-items: flex-start;
      }
      .leftFooter {
        flex-direction: column;
        align-items: stretch;
      }
      .footerActions {
        width: 100%;
      }
      .ghostBtn,
      .primaryBtn {
        flex: 1;
      }
    }
  </style>
</head>
<body>
  <div class="top">
    <div class="brand">
      <div class="brandMark"></div>
      <div>HRClaw · 高级搜索</div>
    </div>
    <div class="topNav">
      <span>用户：__USERNAME__</span>
      <div class="navGroup">
        <span class="navLabel">流程</span>
        <a href="/hr/tasks">任务执行</a>
        <a href="/hr/checklist">Checklist</a>
        <a href="/hr/workbench">推荐处理台</a>
      </div>
      <div class="navGroup">
        <span class="navLabel">当前页</span>
        <a href="/hr/search">高级搜索</a>
      </div>
      <button id="logoutBtn" type="button">退出</button>
    </div>
  </div>

  <div class="wrap">
    <div class="searchShell">
      <aside class="leftPanel">
        <div>
          <h1 class="panelTitle">招聘要求</h1>
          <div class="panelSub">按 BOSS 高级搜索的方式整理必备条件和加分项，系统会自动拼成查询语句，并继续保留本地向量检索与解释能力。</div>
        </div>

        <div class="roleSelect">
          <input id="jobTitle" placeholder="python开发工程师 · 武汉·江夏区 · 12-14K" />
          <span class="caret"></span>
        </div>

        <section class="section">
          <div class="sectionHead">
            <div class="sectionLabel">必备条件</div>
            <button class="addConditionBtn" type="button" data-add-kind="must">添加条件 ⊕</button>
          </div>
          <div class="conditionList" id="mustList"></div>
        </section>

        <section class="section">
          <div class="sectionHead">
            <div class="sectionLabel">加分项</div>
            <button class="addConditionBtn" type="button" data-add-kind="bonus">添加条件 ⊕</button>
          </div>
          <div class="conditionList" id="bonusList"></div>
        </section>

        <div class="leftFormFooter">
          <div class="miniGrid">
            <div class="miniField">
              <label>城市</label>
              <input id="location" placeholder="北京" />
            </div>
            <div class="miniField">
              <label>最低年限</label>
              <input id="yearsMin" type="number" min="0" max="30" step="0.5" placeholder="3" />
            </div>
            <div class="miniField">
              <label>最低学历</label>
              <select id="educationMin">
                <option value="">不限</option>
                <option value="大专">大专</option>
                <option value="本科">本科</option>
                <option value="硕士">硕士</option>
                <option value="博士">博士</option>
              </select>
            </div>
            <div class="miniField">
              <label>返回数量</label>
              <input id="topK" type="number" min="1" max="20" value="20" />
            </div>
          </div>

          <div class="notesBox">
            <div class="miniField">
              <label>补充说明 / JD 原文</label>
              <textarea id="queryNotes" placeholder="可选：补充业务背景、行业要求、排除条件或整段 JD 原文。"></textarea>
            </div>
          </div>

          <div class="explainRow">
            <span>生成 AI 推荐理由、风险点和建议追问</span>
            <label class="switch">
              <input id="explain" type="checkbox" checked />
              <span class="slider"></span>
            </label>
          </div>

          <div id="metaBox" class="metaBox">等待操作...</div>
        </div>

        <div class="leftFooter">
          <div class="quota">
            <span class="quotaSpark"></span>
            <span>今日匹配次数剩余：<strong>5次</strong></span>
          </div>
          <div class="footerActions">
            <button id="upsertBtn" class="ghostBtn" type="button">回灌索引</button>
            <button id="searchBtn" class="primaryBtn" type="button">立即匹配</button>
          </div>
        </div>
      </aside>

      <section class="rightPanel">
        <div class="resultsTop">
          <div>
            <div class="resultsTitle">推荐简历</div>
            <div id="resultsStatus" class="resultsStatus">等待开始匹配...</div>
          </div>
          <div class="subscriptionBox">
            <span>订阅：暂无</span>
            <span class="caret" style="transform: rotate(45deg) translateY(-1px); width:10px; height:10px;"></span>
          </div>
        </div>
        <div class="resultsWrap">
          <div id="results" class="resultsList"></div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const jobTitleInput = document.getElementById("jobTitle");
    const mustList = document.getElementById("mustList");
    const bonusList = document.getElementById("bonusList");
    const locationInput = document.getElementById("location");
    const yearsMinInput = document.getElementById("yearsMin");
    const educationMinInput = document.getElementById("educationMin");
    const topKInput = document.getElementById("topK");
    const queryNotes = document.getElementById("queryNotes");
    const explainInput = document.getElementById("explain");
    const upsertBtn = document.getElementById("upsertBtn");
    const searchBtn = document.getElementById("searchBtn");
    const metaBox = document.getElementById("metaBox");
    const resultsEl = document.getElementById("results");
    const resultsStatus = document.getElementById("resultsStatus");

    function esc(value) {
      if (value === null || value === undefined) return "";
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function initialsFromName(name) {
      const raw = String(name || "").trim();
      if (!raw) return "人";
      return raw.slice(0, 1).toUpperCase();
    }

    function buildConditionRow(kind, value = "") {
      const row = document.createElement("div");
      row.className = "conditionRow";
      row.innerHTML = `
        <input type="text" placeholder="${kind === "must" ? "例如：Python开发 / Linux / Charles" : "例如：在线教育 / AI 项目 / SE 经验"}" value="${esc(value)}" />
        <button class="trashBtn" type="button" title="删除条件">🗑</button>
      `;
      const removeBtn = row.querySelector(".trashBtn");
      removeBtn.addEventListener("click", () => {
        const container = kind === "must" ? mustList : bonusList;
        if (container.children.length <= 1) {
          row.querySelector("input").value = "";
          return;
        }
        row.remove();
      });
      return row;
    }

    function ensureBaseRows() {
      if (!mustList.children.length) {
        mustList.appendChild(buildConditionRow("must"));
        mustList.appendChild(buildConditionRow("must"));
      }
      if (!bonusList.children.length) {
        bonusList.appendChild(buildConditionRow("bonus"));
        bonusList.appendChild(buildConditionRow("bonus"));
        bonusList.appendChild(buildConditionRow("bonus"));
      }
    }

    function collectConditions(container) {
      return Array.from(container.querySelectorAll("input"))
        .map((input) => input.value.trim())
        .filter(Boolean);
    }

    function setMeta(message) {
      metaBox.textContent = message;
    }

    function setStatus(message, highlight = "") {
      if (highlight) {
        resultsStatus.innerHTML = `${esc(message)} <strong>${esc(highlight)}</strong>`;
        return;
      }
      resultsStatus.textContent = message;
    }

    function renderEmpty(message) {
      resultsEl.innerHTML = `<div class="emptyState">${esc(message)}</div>`;
    }

    function renderResults(items, runMeta = {}) {
      if (!items || !items.length) {
        renderEmpty("暂无结果。请先回灌索引，或调整左侧招聘要求。");
        return;
      }
      resultsEl.innerHTML = items.map((item, index) => {
        const recommendation = String(item.final_recommendation || item.explanation_status || "review");
        const recommendationLabel = recommendation === "recommend" ? "建议沟通" : (recommendation === "reject" ? "暂不沟通" : "继续复核");
        const badgeClass = recommendation === "recommend" ? "recommend" : (recommendation === "reject" ? "reject" : "review");
        const links = item.resume_entry || {};
        const evidence = (item.matched_evidence || []).slice(0, 2);
        const reason = evidence.length ? evidence.join("；") : "命中本地简历库中的多维证据，建议进一步查看详情确认。";
        const metaBits = [
          item.years_experience ? `${item.years_experience}年` : "",
          item.education_level || "",
          item.city || "",
        ].filter(Boolean);
        const riskTags = (item.risk_flags || item.gaps || []).slice(0, 2);
        const askTags = (item.interview_questions || []).slice(0, 2);
        const statusText = index === 0 && runMeta.completedAt
          ? `${runMeta.completedAt} 匹配完成`
          : `${runMeta.completedAt || "刚刚"} 推荐候选人`;
        return `
          <article class="candidateCard">
            <div class="candidateTopline">
              <div>${esc(statusText)}</div>
              <div class="candidateBadge ${badgeClass}">${esc(recommendationLabel)} · ${esc(item.hard_filter_pass ? "条件通过" : "条件待确认")}</div>
            </div>
            <div class="candidateRow">
              <div class="avatar">${esc(initialsFromName(item.name))}</div>
              <div>
                <div class="candidateName">${esc(item.name || "未命名候选人")}</div>
                <div class="metaLine">
                  ${metaBits.map((bit, idx) => `<span>${esc(bit)}</span>${idx < metaBits.length - 1 ? '<span class="dotSep">|</span>' : ''}`).join("")}
                </div>
                <div class="factRow">
                  <div class="factItem">
                    <span class="factIcon">💼</span>
                    <span class="factText">${esc(item.latest_company || "-")} · ${esc(item.latest_title || "-")}</span>
                  </div>
                  <div class="factItem">
                    <span class="factIcon">🎓</span>
                    <span class="factText">${esc(item.education_level || "-")} · ${esc(item.city || "-")}</span>
                  </div>
                </div>
                <div class="reasonRow">
                  <div class="reasonBadge">AI推荐理由</div>
                  <div class="reasonText">${esc(reason)}</div>
                </div>
                <div class="chipRow">
                  ${riskTags.map((entry) => `<span class="miniChip risk">风险 · ${esc(entry)}</span>`).join("")}
                  ${askTags.map((entry) => `<span class="miniChip ask">追问 · ${esc(entry)}</span>`).join("")}
                </div>
              </div>
              <div class="candidateSide">
                <div class="scorePill"><strong>${esc(item.total_score ?? "-")}</strong><span>分</span></div>
                ${links.detail_api_path ? `<a class="actionBtn" target="_blank" href="${esc(links.detail_api_path)}">查看详情</a>` : `<span class="actionBtn" style="opacity:.5;cursor:not-allowed;">待补详情</span>`}
                <div class="sideLinks">
                  ${links.screenshot_api_path ? `<a class="textLink" target="_blank" href="${esc(links.screenshot_api_path)}">查看截图</a>` : ""}
                  <span class="textLink">Profile: ${esc(item.resume_profile_id)}</span>
                </div>
              </div>
            </div>
          </article>
        `;
      }).join("");
    }

    function currentTimestampLabel() {
      const now = new Date();
      return `${now.getMonth() + 1}月${now.getDate()}日 ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
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

    async function getJson(path) {
      const res = await fetch(path);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `请求失败(${res.status})`);
      return data;
    }

    function composeQuery() {
      const mustValues = collectConditions(mustList);
      const bonusValues = collectConditions(bonusList);
      const parts = [];
      if (jobTitleInput.value.trim()) parts.push(jobTitleInput.value.trim());
      if (mustValues.length) parts.push(`必备：${mustValues.join("；")}`);
      if (bonusValues.length) parts.push(`加分：${bonusValues.join("；")}`);
      if (queryNotes.value.trim()) parts.push(queryNotes.value.trim());
      return {
        rawQuery: parts.join("\\n"),
        mustValues,
        bonusValues,
      };
    }

    async function upsertIndex() {
      upsertBtn.disabled = true;
      setMeta("正在把本地候选人回灌到搜索索引...");
      try {
        const data = await postJson("/api/v3/search/index/upsert", {});
        setMeta(`索引完成\\nProfiles: ${data.upserted_profiles}\\nChunks: ${data.upserted_chunks}\\nDegraded: ${(data.degraded || []).join(", ") || "none"}\\n耗时: ${data.duration_ms}ms`);
      } catch (err) {
        setMeta(`索引失败：${err.message}`);
      } finally {
        upsertBtn.disabled = false;
      }
    }

    async function pollRun(runId) {
      for (let i = 0; i < 20; i += 1) {
        const data = await getJson(`/api/v3/search/runs/${encodeURIComponent(runId)}`);
        renderResults(data.results || [], { completedAt: currentTimestampLabel() });
        setMeta(`Run: ${runId}\\nStatus: ${data.status}\\nDegraded: ${(data.degraded || []).join(", ") || "none"}\\nQueryIntent: ${JSON.stringify(data.query_intent || {}, null, 2)}`);
        setStatus("匹配完成", currentTimestampLabel());
        if (data.status === "completed") return;
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
    }

    async function searchNow() {
      const queryPayload = composeQuery();
      if (!queryPayload.rawQuery.trim()) {
        setMeta("请先填写职位概述或至少一个筛选条件。");
        renderEmpty("请在左侧填写招聘要求后再开始匹配。");
        return;
      }
      searchBtn.disabled = true;
      renderEmpty("正在匹配候选人，请稍候...");
      setStatus("正在匹配中...", "请稍候");
      setMeta("开始搜索...");
      try {
        const filters = {};
        if (locationInput.value.trim()) filters.location = locationInput.value.trim();
        if (yearsMinInput.value.trim()) filters.years_min = Number(yearsMinInput.value);
        if (educationMinInput.value) filters.education_min = educationMinInput.value;
        if (queryPayload.mustValues.length) filters.skills = queryPayload.mustValues;
        const payload = await postJson("/api/v3/search/query", {
          query_text: queryPayload.rawQuery,
          filters,
          top_k: Number(topKInput.value || 20),
          explain: explainInput.checked
        });
        renderResults(payload.results || [], { completedAt: currentTimestampLabel() });
        setStatus(payload.status === "reranking" ? "正在补齐 AI 推荐理由" : "匹配完成", currentTimestampLabel());
        setMeta(`Run: ${payload.search_run_id}\\nStatus: ${payload.status}\\nQueryIntent: ${JSON.stringify(payload.query_intent || {}, null, 2)}`);
        if (payload.status === "reranking") {
          await pollRun(payload.search_run_id);
        }
      } catch (err) {
        setMeta(`搜索失败：${err.message}`);
        renderEmpty(err.message);
        setStatus("匹配失败");
      } finally {
        searchBtn.disabled = false;
      }
    }

    document.querySelectorAll("[data-add-kind]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-add-kind");
        const target = kind === "must" ? mustList : bonusList;
        target.appendChild(buildConditionRow(kind));
      });
    });

    ensureBaseRows();
    renderEmpty("在左侧填写招聘要求后，系统会在这里展示推荐简历。");

    upsertBtn.addEventListener("click", upsertIndex);
    searchBtn.addEventListener("click", searchNow);
    document.getElementById("logoutBtn").addEventListener("click", async () => {
      try {
        await postJson("/api/logout", {});
      } catch (_) {}
      window.location.href = "/login";
    });
  </script>
</body>
</html>""".replace("__USERNAME__", username)


def _workbench_page_html(username: str) -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>HR 推荐处理台</title>
  <style>
    :root {
      --boss-blue: #00bebd;
      --boss-deep: #0479ff;
      --bg: #f4f8ff;
      --card: rgba(255,255,255,0.94);
      --line: #e4eaf4;
      --text: #17233d;
      --muted: #6d7892;
      --ok: #0e9f6e;
      --warn: #d97706;
      --bad: #dc2626;
      --shadow: 0 18px 42px rgba(27, 59, 117, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(900px 320px at -10% -20%, #d6fffb 0%, transparent 55%),
        radial-gradient(1000px 360px at 100% 0%, #d9e7ff 0%, transparent 58%),
        var(--bg);
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 20px;
      background: rgba(255,255,255,0.72);
      backdrop-filter: blur(18px);
      border-bottom: 1px solid rgba(255,255,255,0.8);
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
      background: linear-gradient(135deg, #5b6cff, #1bd2d1);
      box-shadow: 0 12px 28px rgba(69, 103, 228, 0.26);
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
      background: rgba(255,255,255,0.76);
      border: 1px solid #dde7f4;
    }
    .navLabel {
      font-size: 12px;
      color: var(--muted);
    }
    .topbar a, .topbar button {
      color: var(--text);
      text-decoration: none;
      background: #fff;
      border: 1px solid #d8e2f0;
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 12px;
      cursor: pointer;
    }
    .wrap {
      width: min(100%, 1880px);
      margin: 0 auto;
      padding: 18px 16px 20px;
    }
    .toolbar {
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      background: var(--card);
      border: 1px solid rgba(255,255,255,0.82);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding: 16px;
    }
    .toolbar input,
    .toolbar select,
    .toolbar button {
      height: 40px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      padding: 0 12px;
      color: var(--text);
    }
    .toolbar button {
      cursor: pointer;
      border: 0;
      color: #fff;
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
      font-weight: 700;
    }
    .toolbar label {
      display: grid;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
    }
    .toolbar .checkWrap {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-top: 24px;
      font-size: 13px;
      color: var(--muted);
    }
    .meta {
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }
    .shell {
      margin-top: 16px;
      display: grid;
      grid-template-columns: 460px minmax(0, 1fr);
      gap: 16px;
      min-height: calc(100vh - 220px);
    }
    .panel {
      background: var(--card);
      border: 1px solid rgba(255,255,255,0.82);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
      min-width: 0;
    }
    .queueHead,
    .detailHead {
      padding: 18px 20px 14px;
      border-bottom: 1px solid #edf2f8;
    }
    .queueHead h1,
    .detailHead h1 {
      margin: 0;
      font-size: 24px;
    }
    .sub {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .queueList {
      padding: 10px 12px 14px;
      max-height: calc(100vh - 300px);
      overflow: auto;
    }
    .queueCard {
      border: 1px solid #e8eef6;
      border-radius: 18px;
      padding: 14px;
      background: linear-gradient(180deg, #fff, #fbfdff);
      margin-bottom: 10px;
      cursor: pointer;
      transition: .15s ease;
    }
    .queueCard:hover,
    .queueCard.active {
      border-color: #9dc4ff;
      box-shadow: 0 10px 26px rgba(42, 88, 190, 0.12);
      transform: translateY(-1px);
    }
    .queueTop {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .queueName {
      font-size: 20px;
      font-weight: 700;
    }
    .queueMeta,
    .queueSummary {
      margin-top: 8px;
      color: #33496f;
      font-size: 13px;
      line-height: 1.6;
    }
    .scoreBadge,
    .stageBadge,
    .decisionBadge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid #dfe8f4;
      background: #f6f8fc;
      color: #456083;
    }
    .scoreBadge strong {
      font-size: 16px;
      margin-right: 4px;
      color: #1a4177;
    }
    .decisionBadge.recommend { color: var(--ok); background: rgba(14,159,110,0.1); border-color: rgba(14,159,110,0.18); }
    .decisionBadge.review { color: #6c55ff; background: rgba(108,85,255,0.11); border-color: rgba(108,85,255,0.18); }
    .decisionBadge.reject { color: var(--bad); background: rgba(220,38,38,0.1); border-color: rgba(220,38,38,0.18); }
    .chips {
      margin-top: 10px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid #e4ebf5;
      background: #f7f9fc;
      color: #667590;
      font-size: 12px;
    }
    .chip.warn {
      color: var(--warn);
      background: rgba(217,119,6,0.09);
      border-color: rgba(217,119,6,0.16);
    }
    .chip.ok {
      color: var(--ok);
      background: rgba(14,159,110,0.1);
      border-color: rgba(14,159,110,0.16);
    }
    .detailBody {
      padding: 18px 20px 22px;
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(360px, 420px);
      gap: 18px;
      min-height: 0;
    }
    .sectionCard {
      border: 1px solid #e7edf6;
      border-radius: 18px;
      padding: 16px;
      background: linear-gradient(180deg, #fff, #fcfdff);
      margin-bottom: 14px;
    }
    .sectionCard h2 {
      margin: 0 0 12px;
      font-size: 16px;
    }
    .facts {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .fact {
      padding: 12px;
      border-radius: 14px;
      background: #f7f9fc;
      border: 1px solid #e8eef7;
      font-size: 13px;
      line-height: 1.5;
    }
    .fact strong {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
      font-weight: 600;
    }
    .detailText {
      color: #314565;
      font-size: 14px;
      line-height: 1.75;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .actionGrid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .quickBtn,
    .saveBtn,
    .secondaryBtn {
      height: 40px;
      border-radius: 12px;
      border: 1px solid #dbe5f1;
      background: #fff;
      color: #35507d;
      cursor: pointer;
      font-weight: 700;
    }
    .saveBtn {
      border: 0;
      color: #fff;
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
    }
    .quickBtn.primary {
      color: #fff;
      border: 0;
      background: linear-gradient(110deg, #102347, #0ecfd0);
    }
    .quickBtn.warn {
      color: #935602;
      background: rgba(217,119,6,0.08);
      border-color: rgba(217,119,6,0.18);
    }
    .quickBtn.danger {
      color: #ab1e1e;
      background: rgba(220,38,38,0.08);
      border-color: rgba(220,38,38,0.18);
    }
    .formGrid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .field {
      display: grid;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
    }
    .field input,
    .field select,
    .field textarea {
      width: 100%;
      border: 1px solid #dfe7f1;
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 14px;
      color: var(--text);
      background: #fff;
    }
    .field textarea {
      min-height: 82px;
      resize: vertical;
    }
    .field.full {
      grid-column: 1 / -1;
    }
    .toggleRow {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
    }
    .toggleRow label {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: #4b5f82;
    }
    .tagList,
    .timelineList {
      display: grid;
      gap: 10px;
    }
    .tagItem,
    .timelineItem {
      border-radius: 14px;
      border: 1px solid #e6edf6;
      background: #f8fbff;
      padding: 12px;
      font-size: 13px;
      line-height: 1.6;
      color: #3d5174;
    }
    .timelineItem strong {
      color: var(--text);
    }
    .detailLinks {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
    }
    .detailLinks a {
      color: #3360c7;
      text-decoration: none;
      font-size: 13px;
    }
    .detailEmpty {
      display: grid;
      place-items: center;
      min-height: 520px;
      color: var(--muted);
      font-size: 15px;
      padding: 20px;
      text-align: center;
    }
    .statusBar {
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      white-space: pre-wrap;
      line-height: 1.6;
    }
    @media (max-width: 1280px) {
      .toolbar { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
      .shell { grid-template-columns: 1fr; }
      .detailBody { grid-template-columns: 1fr; }
    }
    @media (max-width: 860px) {
      .toolbar { grid-template-columns: 1fr 1fr; }
      .facts,
      .formGrid,
      .actionGrid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="brandMark"></div>
      <div>HRClaw · HR 推荐处理台</div>
    </div>
    <div class="topNav">
      <span>用户：__USERNAME__</span>
      <div class="navGroup">
        <span class="navLabel">流程</span>
        <a href="/hr/tasks">任务执行</a>
        <a href="/hr/checklist">Checklist</a>
      </div>
      <div class="navGroup">
        <span class="navLabel">搜索</span>
        <a href="/hr/search">高级搜索</a>
      </div>
      <div class="navGroup">
        <span class="navLabel">当前页</span>
        <a href="/hr/workbench">推荐处理台</a>
      </div>
      <button id="logoutBtn" type="button">退出</button>
    </div>
  </div>

  <div class="wrap">
    <div class="toolbar">
      <label>关键词
        <input id="keyword" placeholder="姓名 / 公司 / 职位 / external_id" />
      </label>
      <label>任务
        <select id="taskId"><option value="">全部任务</option></select>
      </label>
      <label>岗位
        <select id="jobId"><option value="">全部岗位</option></select>
      </label>
      <label>来源
        <select id="sourceFilter">
          <option value="">全部来源</option>
          <option value="boss_extension">插件入库</option>
          <option value="pipeline">任务采集</option>
        </select>
      </label>
      <label>当前阶段
        <select id="stage"><option value="">全部阶段</option></select>
      </label>
      <label>系统决策
        <select id="decision">
          <option value="">全部决策</option>
          <option value="recommend">建议沟通</option>
          <option value="review">继续复核</option>
          <option value="reject">暂不沟通</option>
        </select>
      </label>
      <label>打招呼状态
        <select id="greetStatus">
          <option value="">全部状态</option>
          <option value="success">成功</option>
          <option value="skipped">已跳过</option>
          <option value="failed">失败</option>
        </select>
      </label>
      <label>Owner
        <input id="ownerFilter" placeholder="hr_1 / Lisa" />
      </label>
      <label>返回数量
        <input id="limit" type="number" min="1" max="500" value="120" />
      </label>
      <div class="checkWrap"><input id="unreviewedOnly" type="checkbox" /><span>只看未复核</span></div>
      <div class="checkWrap"><input id="reusableOnly" type="checkbox" /><span>只看可复用</span></div>
      <div class="checkWrap"><input id="needsFollowUp" type="checkbox" /><span>只看待跟进</span></div>
      <div class="checkWrap"><input id="manualLockedOnly" type="checkbox" /><span>只看人工接管</span></div>
      <button id="refreshBtn" type="button">刷新队列</button>
    </div>
    <div id="meta" class="meta">加载中...</div>

    <div class="shell">
      <section class="panel">
        <div class="queueHead">
          <h1>候选人队列</h1>
          <div class="sub">把推荐牛人的判断、沟通和沉淀动作统一放在一个页面里处理。点击左侧候选人后，右侧可直接保存阶段、标签和跟进计划。</div>
        </div>
        <div id="queueList" class="queueList"></div>
      </section>

      <section class="panel">
        <div class="detailHead">
          <h1>候选人详情与动作</h1>
          <div class="sub">先看系统判断和证据，再给出标准化动作，方便后续复用和协同。</div>
        </div>
        <div id="detailRoot" class="detailBody">
          <div class="detailEmpty">请选择左侧候选人，开始处理推荐结果。</div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const taskIdInput = document.getElementById("taskId");
    const jobIdInput = document.getElementById("jobId");
    const sourceFilterInput = document.getElementById("sourceFilter");
    const keywordInput = document.getElementById("keyword");
    const stageInput = document.getElementById("stage");
    const decisionInput = document.getElementById("decision");
    const greetStatusInput = document.getElementById("greetStatus");
    const ownerFilterInput = document.getElementById("ownerFilter");
    const limitInput = document.getElementById("limit");
    const unreviewedOnlyInput = document.getElementById("unreviewedOnly");
    const reusableOnlyInput = document.getElementById("reusableOnly");
    const needsFollowUpInput = document.getElementById("needsFollowUp");
    const manualLockedOnlyInput = document.getElementById("manualLockedOnly");
    const refreshBtn = document.getElementById("refreshBtn");
    const queueList = document.getElementById("queueList");
    const detailRoot = document.getElementById("detailRoot");
    const meta = document.getElementById("meta");

    const stageLabels = {
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
      do_not_contact: "不再联系",
    };
    const reasonCodeLabels = {
      skills_match: "技能匹配",
      skills_gap: "技能不匹配",
      industry_fit: "行业匹配",
      industry_gap: "行业不匹配",
      years_gap: "年限不足",
      education_gap: "学历不符",
      salary_gap: "薪资不符",
      city_gap: "城市不符",
      resume_incomplete: "简历信息待补充",
      candidate_positive: "候选人意向积极",
      reusable_pool: "适合沉淀人才库",
      duplicate_candidate: "重复候选人",
      do_not_contact: "不再联系",
    };
    const finalDecisionLabels = {
      recommend: "建议沟通",
      review: "继续复核",
      reject: "暂不沟通",
      talent_pool: "沉淀人才库",
      pending: "待处理",
      reviewed_completed: "已完成复核",
      confirmed: "已确认",
    };
    const systemDecisionLabels = {
      recommend: "建议沟通",
      review: "继续复核",
      reject: "暂不沟通",
    };
    const reviewActionLabels = {
      approve: "通过复核",
      reject: "复核淘汰",
      hold: "暂缓处理",
      mark_reviewed: "已人工复核",
    };
    const confirmActionLabels = {
      send_greeting: "确认打招呼",
      download_resume: "确认下载简历",
      advance_pipeline: "确认推进流程",
    };
    const candidateActionTypeLabels = {
      send_greeting: "打招呼",
      download_resume: "下载简历",
      advance_pipeline: "推进流程",
    };
    const candidateActionStatusLabels = {
      success: "成功",
      skipped: "已跳过",
      failed: "失败",
      pending: "待处理",
      confirmed: "已确认",
    };

    const quickActions = {
      toContact: {current_stage: "to_contact", final_decision: "recommend", reason_code: "skills_match", review_action: "approve"},
      needInfo: {current_stage: "needs_followup", final_decision: "review", reason_code: "resume_incomplete", review_action: "hold"},
      keepPool: {current_stage: "talent_pool", final_decision: "talent_pool", reason_code: "reusable_pool", reusable_flag: true},
      invited: {current_stage: "interview_invited", final_decision: "recommend", reason_code: "candidate_positive", review_action: "approve"},
      reject: {current_stage: "rejected", final_decision: "reject", reason_code: "skills_gap", review_action: "reject"},
      block: {current_stage: "do_not_contact", final_decision: "reject", reason_code: "do_not_contact", do_not_contact: true, review_action: "reject"},
    };

    let currentItems = [];
    let selectedCandidateId = null;

    function esc(value) {
      if (value === null || value === undefined) return "";
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function tagClass(value) {
      if (value === "recommend") return "decisionBadge recommend";
      if (value === "reject") return "decisionBadge reject";
      return "decisionBadge review";
    }

    function fmtTime(value) {
      return value ? esc(value) : "-";
    }

    function safeTextList(values, limit = 2) {
      return (values || []).filter(Boolean).slice(0, limit);
    }

    function prettyValue(value) {
      if (value === null || value === undefined || value === "") return "";
      return String(value);
    }

    function joinHumanParts(parts) {
      return parts.filter(Boolean).join("；");
    }

    function timelineEventTitle(entry) {
      const eventType = String(entry.event_type || "");
      if (eventType === "tag_added") return "已添加标签";
      if (eventType === "stage_updated") return "处理状态已更新";
      if (eventType === "review_action") return "已保存复核结果";
      if (eventType === "follow_up_scheduled") return "已设置跟进计划";
      if (eventType === "confirm_action") return "已确认系统动作";
      if (eventType === "seeded") return "系统初始化记录";
      return "候选人状态更新";
    }

    function timelineEventSummary(entry) {
      const eventType = String(entry.event_type || "");
      const payload = entry.event_payload || {};
      if (eventType === "tag_added") {
        return joinHumanParts([
          payload.tag ? `添加标签：${payload.tag}` : "",
          payload.tag_type && payload.tag_type !== "manual" ? `类型：${payload.tag_type}` : "",
        ]) || "已新增候选人标签。";
      }
      if (eventType === "stage_updated") {
        return joinHumanParts([
          payload.current_stage ? `阶段变更为：${stageLabels[payload.current_stage] || payload.current_stage}` : "",
          payload.reason_code ? `原因：${reasonCodeLabels[payload.reason_code] || payload.reason_code}` : "",
          payload.final_decision ? `结论：${finalDecisionLabels[payload.final_decision] || payload.final_decision}` : "",
          payload.last_contact_result ? `沟通结果：${payload.last_contact_result}` : "",
          payload.next_follow_up_at ? `下次跟进：${payload.next_follow_up_at}` : "",
          payload.reusable_flag ? "已标记为可复用" : "",
          payload.do_not_contact ? "已标记为不再联系" : "",
          payload.reason_notes ? `备注：${payload.reason_notes}` : "",
        ]) || "已更新候选人处理状态。";
      }
      if (eventType === "review_action") {
        return joinHumanParts([
          payload.action ? `复核动作：${reviewActionLabels[payload.action] || payload.action}` : "",
          payload.final_decision ? `复核结论：${finalDecisionLabels[payload.final_decision] || payload.final_decision}` : "",
          payload.comment ? `备注：${payload.comment}` : "",
        ]) || "已记录 HR 复核结果。";
      }
      if (eventType === "follow_up_scheduled") {
        return joinHumanParts([
          payload.next_follow_up_at ? `下次跟进时间：${payload.next_follow_up_at}` : "",
          payload.last_contact_result ? `当前沟通结果：${payload.last_contact_result}` : "",
          payload.comment ? `备注：${payload.comment}` : "",
        ]) || "已保存跟进计划。";
      }
      if (eventType === "confirm_action") {
        return joinHumanParts([
          payload.action ? `确认动作：${confirmActionLabels[payload.action] || payload.action}` : "",
          payload.final_decision ? `处理结果：${finalDecisionLabels[payload.final_decision] || payload.final_decision}` : "",
          payload.comment ? `备注：${payload.comment}` : "",
        ]) || "已确认系统动作。";
      }
      if (eventType === "seeded") {
        return "系统已为该候选人初始化记录。";
      }
      const payloadValues = Object.values(payload || {}).map(prettyValue).filter(Boolean);
      return payloadValues.length ? payloadValues.join("；") : "已记录一条候选人操作。";
    }

    function reviewSummary(review) {
      if (!review) return "暂无";
      return joinHumanParts([
        review.action ? `${reviewActionLabels[review.action] || review.action}` : "",
        review.final_decision ? `${finalDecisionLabels[review.final_decision] || review.final_decision}` : "",
        review.reviewer ? `操作人：${review.reviewer}` : "",
      ]) || "已保存复核结果";
    }

    function actionSummary(action) {
      if (!action) return "";
      const detail = action.detail || {};
      return joinHumanParts([
        action.action_type ? `${candidateActionTypeLabels[action.action_type] || action.action_type}` : "",
        action.status ? `${candidateActionStatusLabels[action.status] || action.status}` : "",
        detail.reason ? `原因：${detail.reason}` : "",
      ]);
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

    function buildQuery() {
      const params = new URLSearchParams();
      if (taskIdInput.value) params.set("task_id", taskIdInput.value);
      if (jobIdInput.value) params.set("job_id", jobIdInput.value);
      if (sourceFilterInput.value) params.set("source", sourceFilterInput.value);
      if (keywordInput.value.trim()) params.set("keyword", keywordInput.value.trim());
      if (stageInput.value) params.set("stage", stageInput.value);
      if (decisionInput.value) params.set("decision", decisionInput.value);
      if (greetStatusInput.value) params.set("greet_status", greetStatusInput.value);
      if (ownerFilterInput.value.trim()) params.set("owner", ownerFilterInput.value.trim());
      if (unreviewedOnlyInput.checked) params.set("unreviewed_only", "1");
      if (reusableOnlyInput.checked) params.set("reusable_only", "1");
      if (needsFollowUpInput.checked) params.set("needs_follow_up", "1");
      if (manualLockedOnlyInput.checked) params.set("manual_stage_locked", "1");
      params.set("limit", String(Number(limitInput.value || 120)));
      return params.toString();
    }

    function renderQueue(items) {
      if (!items.length) {
        queueList.innerHTML = '<div class="detailEmpty" style="min-height:220px;">暂无候选人，先运行 recommend 任务或调整筛选条件。</div>';
        detailRoot.innerHTML = '<div class="detailEmpty">请选择左侧候选人，开始处理推荐结果。</div>';
        return;
      }
      queueList.innerHTML = items.map((item) => {
        const state = item.pipeline_state || {};
        const stageText = stageLabels[state.current_stage] || state.current_stage || "新入库";
        const reasons = safeTextList(item.review_reasons && item.review_reasons.length ? item.review_reasons : item.hard_filter_fail_reasons, 2);
        return `
          <article class="queueCard ${item.candidate_id === selectedCandidateId ? "active" : ""}" data-candidate-id="${esc(item.candidate_id)}">
            <div class="queueTop">
              <div>
                <div class="queueName">${esc(item.name || "未命名候选人")}</div>
                <div class="queueMeta">${esc(item.current_company || "-")} · ${esc(item.current_title || "-")}</div>
              </div>
              <div class="scoreBadge"><strong>${item.total_score === null || item.total_score === undefined ? "-" : esc(Number(item.total_score).toFixed(1))}</strong>分</div>
            </div>
            <div class="queueMeta">${esc(item.years_experience || "-")} 年 / ${esc(item.education_level || "-")} / ${esc(item.location || "-")}</div>
            <div class="chips">
              <span class="stageBadge">${esc(stageText)}</span>
              <span class="chip">${esc(item.source === "boss_extension" ? "插件入库" : "任务采集")}</span>
              <span class="${tagClass(item.decision)}">${esc(systemDecisionLabels[item.decision || "review"] || item.decision || "继续复核")}</span>
              ${item.greet_status ? `<span class="chip ok">打招呼 · ${esc(candidateActionStatusLabels[item.greet_status] || item.greet_status)}</span>` : ""}
              ${state.reusable_flag ? '<span class="chip ok">可复用</span>' : ""}
              ${state.do_not_contact ? '<span class="chip warn">不再联系</span>' : ""}
            </div>
            <div class="queueSummary">${esc((reasons.join("；") || item.raw_summary || "等待查看详情").slice(0, 120))}</div>
            <div class="chips">
              ${(item.tags || []).slice(0, 3).map((tag) => `<span class="chip">${esc(tag)}</span>`).join("")}
            </div>
          </article>
        `;
      }).join("");
    }

    function renderDetail(data) {
      const candidate = data.candidate || {};
      const score = data.score || {};
      const snapshot = data.snapshot || {};
      const task = data.task || {};
      const job = data.job || {};
      const state = data.pipeline_state || {};
      const reviews = data.reviews || [];
      const actions = data.actions || [];
      const tags = data.tags || [];
      const timeline = data.timeline || [];
      const reasons = safeTextList(score.review_reasons && score.review_reasons.length ? score.review_reasons : score.hard_filter_fail_reasons, 4);
      detailRoot.innerHTML = `
        <div>
          <div class="sectionCard">
            <h2>${esc(candidate.name || "未命名候选人")}</h2>
            <div class="facts">
              <div class="fact"><strong>当前职位</strong>${esc(candidate.current_title || "-")}</div>
              <div class="fact"><strong>当前公司</strong>${esc(candidate.current_company || "-")}</div>
              <div class="fact"><strong>经验 / 学历</strong>${esc(candidate.years_experience || "-")} 年 / ${esc(candidate.education_level || "-")}</div>
              <div class="fact"><strong>城市 / 薪资</strong>${esc(candidate.location || "-")} / ${esc(candidate.expected_salary || "-")}</div>
              <div class="fact"><strong>任务 / 岗位</strong>${esc(task.id || "-")} / ${esc(job.name || task.job_id || "-")}</div>
              <div class="fact"><strong>来源</strong>${esc(candidate.source === "boss_extension" ? "插件入库" : "任务采集")}</div>
              <div class="fact"><strong>系统决策</strong>${esc(systemDecisionLabels[score.decision] || score.decision || "-")} · ${score.total_score === null || score.total_score === undefined ? "-" : Number(score.total_score).toFixed(2)} 分</div>
            </div>
            <div class="detailLinks">
              <a target="_blank" href="/api/candidates/${esc(candidate.id)}">详情 JSON</a>
              ${snapshot.screenshot_path ? `<a target="_blank" href="/api/candidates/${esc(candidate.id)}/screenshot">简历截图</a>` : ""}
            </div>
          </div>

          <div class="sectionCard">
            <h2>系统判断与证据</h2>
            <div class="chips">
              ${(reasons.length ? reasons : ["暂无系统理由"]).map((entry) => `<span class="chip ${score.hard_filter_pass ? "ok" : "warn"}">${esc(entry)}</span>`).join("")}
            </div>
            <div class="detailText" style="margin-top:12px;">${esc(snapshot.extracted_text || candidate.raw_summary || "暂无结构化摘要。")}</div>
          </div>

          <div class="sectionCard">
            <h2>标签</h2>
            <div class="chips" id="tagChips">
              ${tags.length ? tags.map((tag) => `<span class="chip">${esc(tag.tag)}</span>`).join("") : '<span class="chip">暂无标签</span>'}
            </div>
            <div class="formGrid" style="margin-top:12px;">
              <label class="field full">新增标签
                <div style="display:flex; gap:10px;">
                  <input id="tagInput" placeholder="例如：在线教育测试 / 北京自动化测试" />
                  <button id="addTagBtn" class="secondaryBtn" type="button" style="min-width:96px;">添加标签</button>
                </div>
              </label>
            </div>
          </div>

          <div class="sectionCard">
            <h2>时间线</h2>
            <div class="timelineList">
              ${timeline.length ? timeline.map((entry) => `
                <div class="timelineItem">
                  <strong>${esc(timelineEventTitle(entry))}</strong><br/>
                  ${esc(entry.operator || "system")} · ${fmtTime(entry.created_at)}<br/>
                  <span>${esc(timelineEventSummary(entry))}</span>
                </div>
              `).join("") : '<div class="timelineItem">暂无时间线记录。</div>'}
            </div>
          </div>
        </div>

        <div>
          <div class="sectionCard">
            <h2>快捷动作</h2>
            <div class="actionGrid">
              <button class="quickBtn primary" type="button" data-quick="toContact">建议沟通</button>
              <button class="quickBtn warn" type="button" data-quick="needInfo">待补信息</button>
              <button class="quickBtn" type="button" data-quick="keepPool">加入人才库</button>
              <button class="quickBtn primary" type="button" data-quick="invited">标记已邀约</button>
              <button class="quickBtn danger" type="button" data-quick="reject">暂不沟通</button>
              <button class="quickBtn danger" type="button" data-quick="block">不再联系</button>
            </div>
          </div>

          <div class="sectionCard">
            <h2>处理表单</h2>
            <div class="formGrid">
              <label class="field">Owner
                <input id="ownerInput" value="${esc(state.owner || "")}" placeholder="hr_1" />
              </label>
              <label class="field">当前阶段
                <select id="stageInput">${Object.entries(stageLabels).map(([key, label]) => `<option value="${esc(key)}" ${state.current_stage === key ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>
              </label>
              <label class="field">原因码
                <select id="reasonCodeInput">
                  <option value="">请选择</option>
                  ${["skills_match","skills_gap","industry_fit","industry_gap","years_gap","education_gap","salary_gap","city_gap","resume_incomplete","candidate_positive","reusable_pool","duplicate_candidate","do_not_contact"].map((entry) => `<option value="${esc(entry)}" ${state.reason_code === entry ? "selected" : ""}>${esc(reasonCodeLabels[entry] || entry)}</option>`).join("")}
                </select>
              </label>
              <label class="field">最终决策
                <select id="finalDecisionInput">
                  <option value="">请选择</option>
                  ${["recommend","review","reject","talent_pool","pending"].map((entry) => `<option value="${esc(entry)}" ${state.final_decision === entry ? "selected" : ""}>${esc(finalDecisionLabels[entry] || entry)}</option>`).join("")}
                </select>
              </label>
              <label class="field">最近沟通时间
                <input id="lastContactedAtInput" type="datetime-local" value="${esc(state.last_contacted_at || "")}" />
              </label>
              <label class="field">最近沟通结果
                <input id="lastContactResultInput" value="${esc(state.last_contact_result || "")}" placeholder="已回复 / 待确认 / 无回复" />
              </label>
              <label class="field">下次跟进时间
                <input id="nextFollowUpAtInput" type="datetime-local" value="${esc(state.next_follow_up_at || "")}" />
              </label>
              <label class="field">人才池状态
                <input id="talentPoolStatusInput" value="${esc(state.talent_pool_status || "")}" placeholder="核心储备 / 可二次激活" />
              </label>
              <label class="field full">补充备注
                <textarea id="reasonNotesInput" placeholder="记录 HR 的判断、沟通情况或补充信息。">${esc(state.reason_notes || "")}</textarea>
              </label>
            </div>
            <div class="toggleRow">
              <label><input id="reusableFlagInput" type="checkbox" ${state.reusable_flag ? "checked" : ""} /> 标记为可复用</label>
              <label><input id="doNotContactInput" type="checkbox" ${state.do_not_contact ? "checked" : ""} /> 标记为不再联系</label>
            </div>
            <div class="actionGrid" style="margin-top:12px;">
              <button id="saveStageBtn" class="saveBtn" type="button">保存处理结果</button>
              <button id="saveFollowUpBtn" class="secondaryBtn" type="button">仅保存跟进计划</button>
            </div>
            <div id="detailStatus" class="statusBar">最近复核：${esc(reviews.length ? reviewSummary(reviews[reviews.length - 1]) : "暂无")}\n历史动作：${esc(actions.length ? actions.slice(-3).reverse().map(actionSummary).filter(Boolean).join("；") : "暂无")}</div>
          </div>
        </div>
      `;

      document.querySelectorAll("[data-quick]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const preset = quickActions[btn.getAttribute("data-quick")];
          if (!preset) return;
          try {
            await saveStage(preset);
          } catch (err) {
            alert(`操作失败: ${err.message}`);
          }
        });
      });
      document.getElementById("saveStageBtn").addEventListener("click", async () => {
        try {
          await saveStage();
        } catch (err) {
          alert(`保存失败: ${err.message}`);
        }
      });
      document.getElementById("saveFollowUpBtn").addEventListener("click", async () => {
        try {
          await saveFollowUp();
        } catch (err) {
          alert(`保存失败: ${err.message}`);
        }
      });
      document.getElementById("addTagBtn").addEventListener("click", async () => {
        const tag = document.getElementById("tagInput").value.trim();
        if (!tag) return;
        try {
          await postJson(`/api/candidates/${encodeURIComponent(candidate.id)}/tags`, {
            tag,
            created_by: "hr_ui",
            tag_type: "manual"
          });
          await loadCandidate(candidate.id, false);
          await loadWorkbench(false);
        } catch (err) {
          alert(`添加标签失败: ${err.message}`);
        }
      });
    }

    async function loadCandidate(candidateId, scrollIntoView = true) {
      selectedCandidateId = candidateId;
      const data = await getJson(`/api/hr/workbench/candidates/${encodeURIComponent(candidateId)}`);
      renderQueue(currentItems);
      renderDetail(data);
      if (scrollIntoView) {
        const active = queueList.querySelector(`[data-candidate-id="${CSS.escape(candidateId)}"]`);
        if (active) active.scrollIntoView({block: "nearest"});
      }
    }

    async function saveStage(preset = null) {
      if (!selectedCandidateId) return;
      const payload = {
        operator: "hr_ui",
        owner: document.getElementById("ownerInput").value.trim(),
        current_stage: preset?.current_stage || document.getElementById("stageInput").value,
        reason_code: preset?.reason_code || document.getElementById("reasonCodeInput").value,
        reason_notes: document.getElementById("reasonNotesInput").value.trim(),
        final_decision: preset?.final_decision || document.getElementById("finalDecisionInput").value,
        last_contacted_at: document.getElementById("lastContactedAtInput").value || null,
        last_contact_result: document.getElementById("lastContactResultInput").value.trim() || null,
        next_follow_up_at: document.getElementById("nextFollowUpAtInput").value || null,
        reusable_flag: preset?.reusable_flag ?? document.getElementById("reusableFlagInput").checked,
        do_not_contact: preset?.do_not_contact ?? document.getElementById("doNotContactInput").checked,
        talent_pool_status: document.getElementById("talentPoolStatusInput").value.trim() || null,
        review_action: preset?.review_action || null,
      };
      await postJson(`/api/candidates/${encodeURIComponent(selectedCandidateId)}/stage`, payload);
      await loadWorkbench(false);
      await loadCandidate(selectedCandidateId, false);
    }

    async function saveFollowUp() {
      if (!selectedCandidateId) return;
      await postJson(`/api/candidates/${encodeURIComponent(selectedCandidateId)}/follow-up`, {
        operator: "hr_ui",
        next_follow_up_at: document.getElementById("nextFollowUpAtInput").value || null,
        last_contact_result: document.getElementById("lastContactResultInput").value.trim() || null,
        comment: document.getElementById("reasonNotesInput").value.trim() || null
      });
      await loadWorkbench(false);
      await loadCandidate(selectedCandidateId, false);
    }

    async function loadWorkbench(resetSelection = true) {
      const data = await getJson(`/api/hr/workbench?${buildQuery()}`);
      currentItems = data.items || [];
      const oldTaskId = taskIdInput.value;
      const oldJobId = jobIdInput.value;
      const oldStage = stageInput.value;
      taskIdInput.innerHTML = '<option value="">全部任务</option>' + (data.tasks || []).map((task) => `<option value="${esc(task.id)}">${esc(task.id)} | ${esc(task.job_id)} | ${esc(task.status)}</option>`).join("");
      taskIdInput.value = oldTaskId;
      jobIdInput.innerHTML = '<option value="">全部岗位</option>' + (data.jobs || []).map((job) => `<option value="${esc(job.id)}">${esc(job.name)} (${esc(job.id)})</option>`).join("");
      jobIdInput.value = oldJobId;
      stageInput.innerHTML = '<option value="">全部阶段</option>' + (data.stage_options || []).map((stage) => `<option value="${esc(stage)}">${esc(stageLabels[stage] || stage)}</option>`).join("");
      stageInput.value = oldStage;

      meta.textContent = `候选人数: ${currentItems.length}，任务数: ${(data.tasks || []).length}，推荐处理以“阶段 + 原因码 + 跟进时间”为主线沉淀。`;
      renderQueue(currentItems);
      if (!currentItems.length) return;
      const nextId = (!resetSelection && selectedCandidateId && currentItems.some((item) => item.candidate_id === selectedCandidateId))
        ? selectedCandidateId
        : currentItems[0].candidate_id;
      await loadCandidate(nextId, false);
    }

    queueList.addEventListener("click", async (event) => {
      const card = event.target.closest("[data-candidate-id]");
      if (!card) return;
      const candidateId = card.getAttribute("data-candidate-id");
      if (!candidateId) return;
      try {
        await loadCandidate(candidateId);
      } catch (err) {
        alert(`加载候选人失败: ${err.message}`);
      }
    });

    refreshBtn.addEventListener("click", () => {
      loadWorkbench(false).catch((err) => {
        meta.textContent = `加载失败: ${err.message}`;
      });
    });
    keywordInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        loadWorkbench(true).catch((err) => {
          meta.textContent = `加载失败: ${err.message}`;
        });
      }
    });
    document.getElementById("logoutBtn").addEventListener("click", async () => {
      try {
        await postJson("/api/logout", {});
      } catch (_) {}
      window.location.href = "/login";
    });

    loadWorkbench(true).catch((err) => {
      meta.textContent = `加载失败: ${err.message}`;
      queueList.innerHTML = '<div class="detailEmpty" style="min-height:220px;">加载失败，请刷新后重试。</div>';
      detailRoot.innerHTML = '<div class="detailEmpty">推荐处理台加载失败。</div>';
    });
  </script>
</body>
</html>""".replace("__USERNAME__", username)


def handle_request(handler):
    method = handler.command
    parsed = urlparse(handler.path)
    path = parsed.path

    if method == "GET" and path == "/health":
        return _json(HTTPStatus.OK, {"status": "ok"})

    if method == "GET" and path == "/favicon.ico":
        return _body(HTTPStatus.NO_CONTENT, b"", "image/x-icon")

    if method == "GET" and path.startswith("/admin-static/"):
        return _admin_frontend_asset(path.removeprefix("/admin-static/"))

    if method == "GET" and path == "/":
        if _current_user(handler):
            return _redirect("/hr/tasks")
        return _redirect("/login")

    if method == "GET" and path == "/login":
        if _current_user(handler):
            return _redirect("/hr/tasks")
        query = parse_qs(parsed.query or "")
        next_path = (query.get("next") or ["/hr/tasks"])[0]
        shell = _admin_frontend_shell(
            title="登录 - HRClaw",
            page_key="login",
            fallback_heading="登录后台",
            fallback_description="初始管理员：admin / admin",
            current_path=path,
            next_path=next_path,
        )
        if shell:
            return _html(HTTPStatus.OK, shell)
        return _html(HTTPStatus.OK, _login_page_html(next_path))

    if method == "POST" and path == "/api/login":
        payload = _read_json(handler)
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        user = get_hr_user_by_username(username, include_secret=True)
        if not user or not verify_password(password, str(user.get("password_hash") or "")):
            return _json(HTTPStatus.UNAUTHORIZED, {"error": "用户名或密码错误"})
        if not bool(user.get("active")):
            return _json(HTTPStatus.UNAUTHORIZED, {"error": "账号已停用，请联系管理员"})
        token = secrets.token_urlsafe(24)
        record_hr_user_login(str(user.get("id") or ""))
        _AUTH_SESSIONS[token] = {
            "user_id": str(user.get("id") or ""),
            "username": str(user.get("username") or username),
            "display_name": str(user.get("display_name") or user.get("username") or username),
            "role": str(user.get("role") or "hr"),
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + AUTH_SESSION_MAX_AGE_SECONDS,
        }
        return _json_with_headers(
            HTTPStatus.OK,
            {
                "ok": True,
                "username": str(user.get("username") or username),
                "display_name": str(user.get("display_name") or user.get("username") or username),
                "role": str(user.get("role") or "hr"),
            },
            {"Set-Cookie": _auth_cookie_value(token)},
        )

    if method == "POST" and path == "/api/logout":
        token = _parse_cookies(handler).get(AUTH_COOKIE_NAME)
        if token:
            _AUTH_SESSIONS.pop(token, None)
        return _json_with_headers(HTTPStatus.OK, {"ok": True}, {"Set-Cookie": _clear_auth_cookie_value()})

    if method == "GET" and path == "/api/hr/users":
        auth_error = _require_admin_json(handler)
        if auth_error is not None:
            return auth_error
        return _json(
            HTTPStatus.OK,
            {
                "items": list_hr_users(),
                "current_user_id": _current_user_id(handler),
            },
        )

    if method == "POST" and path == "/api/hr/users":
        auth_error = _require_admin_json(handler)
        if auth_error is not None:
            return auth_error
        payload = _read_json(handler)
        try:
            user = create_hr_user(
                username=str(payload.get("username") or ""),
                password=str(payload.get("password") or ""),
                display_name=str(payload.get("display_name") or "").strip() or None,
                role=str(payload.get("role") or "hr"),
                active=bool(payload.get("active", True)),
                notes=str(payload.get("notes") or "").strip() or None,
                operator=_current_user(handler) or "admin",
            )
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.CREATED, {"ok": True, "user": user})

    if method == "POST" and path.startswith("/api/hr/users/") and path.endswith("/password"):
        auth_error = _require_admin_json(handler)
        if auth_error is not None:
            return auth_error
        user_id = path.removeprefix("/api/hr/users/").removesuffix("/password").strip("/")
        payload = _read_json(handler)
        try:
            user = reset_hr_user_password(
                user_id=user_id,
                password=str(payload.get("password") or ""),
                operator=_current_user(handler) or "admin",
            )
        except LookupError as exc:
            return _json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.OK, {"ok": True, "user": user})

    if method == "POST" and path.startswith("/api/hr/users/"):
        auth_error = _require_admin_json(handler)
        if auth_error is not None:
            return auth_error
        user_id = path.removeprefix("/api/hr/users/").strip("/")
        if "/" in user_id or not user_id:
            return _json(HTTPStatus.NOT_FOUND, {"error": "User not found"})
        payload = _read_json(handler)
        try:
            user = update_hr_user(
                user_id=user_id,
                display_name=str(payload.get("display_name") or "").strip() or None,
                role=str(payload.get("role") or "hr"),
                active=bool(payload.get("active", True)),
                notes=str(payload.get("notes") or "").strip() if "notes" in payload else None,
                operator=_current_user(handler) or "admin",
            )
        except LookupError as exc:
            return _json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.OK, {"ok": True, "user": user})

    page_auth = _require_page_auth(handler, path=path)
    if page_auth is not None:
        return page_auth

    if method == "GET" and path == "/hr/tasks":
        username = _current_user(handler) or AUTH_USERNAME
        shell = _admin_frontend_shell(
            title="HR任务执行 - Recommend 流程",
            page_key="tasks",
            fallback_heading="创建并执行 Recommend 任务",
            fallback_description="保留原有任务执行、会话保存和候选人筛选流程。",
            current_path=path,
            username=username,
            user_role=_current_user_role(handler),
        )
        if shell:
            return _html(HTTPStatus.OK, shell)
        return _html(HTTPStatus.OK, _task_runner_page_html(username))

    if method == "GET" and path == "/hr/search":
        username = _current_user(handler) or AUTH_USERNAME
        shell = _admin_frontend_shell(
            title="高级搜索 - 本地JD搜索引擎",
            page_key="search",
            fallback_heading="高级搜索",
            fallback_description="保留现有语义检索、重排解释和筛选条件。",
            current_path=path,
            username=username,
            user_role=_current_user_role(handler),
        )
        if shell:
            return _html(HTTPStatus.OK, shell)
        return _html(HTTPStatus.OK, _search_page_html(username))

    if method == "GET" and path == "/hr/phase2":
        username = _current_user(handler) or AUTH_USERNAME
        shell = _admin_frontend_shell(
            title="JD评分卡 - 评分卡工作台",
            page_key="phase2",
            fallback_heading="JD评分卡",
            fallback_description="统一维护第一阶段内置 JD评分卡与第二阶段自定义 JD评分卡。",
            current_path=path,
            username=username,
            user_role=_current_user_role(handler),
        )
        if shell:
            return _html(HTTPStatus.OK, shell)
        return _html(HTTPStatus.OK, phase2_page_html(username))

    if method == "GET" and path == "/hr/resume-imports":
        username = _current_user(handler) or AUTH_USERNAME
        shell = _admin_frontend_shell(
            title="简历导入 - 批量导入简历并打分",
            page_key="resume-imports",
            fallback_heading="批量导入简历并打分",
            fallback_description="保留现有导入、OCR、打分和批次回看流程。",
            current_path=path,
            username=username,
            user_role=_current_user_role(handler),
        )
        if shell:
            return _html(HTTPStatus.OK, shell)
        return _html(
            HTTPStatus.OK,
            "<!doctype html><html><body><h1>批量导入简历并打分</h1><p>请构建最新后台前端后访问。</p></body></html>",
        )

    if method == "GET" and path == "/hr/workbench":
        username = _current_user(handler) or AUTH_USERNAME
        shell = _admin_frontend_shell(
            title="HR 推荐处理台",
            page_key="workbench",
            fallback_heading="推荐处理台",
            fallback_description="延续现有处理队列、候选人详情和跟进动作。",
            current_path=path,
            username=username,
            user_role=_current_user_role(handler),
        )
        if shell:
            return _html(HTTPStatus.OK, shell)
        return _html(HTTPStatus.OK, _workbench_page_html(username))

    if method == "GET" and path == "/hr/checklist":
        username = _current_user(handler) or AUTH_USERNAME
        shell = _admin_frontend_shell(
            title="HR 简历评分清单",
            page_key="checklist",
            fallback_heading="HR 简历评分清单",
            fallback_description="继续使用现有清单筛选、打分复核和状态反馈流程。",
            current_path=path,
            username=username,
            user_role=_current_user_role(handler),
        )
        if shell:
            return _html(HTTPStatus.OK, shell)

    if method == "GET" and path == "/hr/users":
        username = _current_user(handler) or AUTH_USERNAME
        user_role = _current_user_role(handler)
        shell = _admin_frontend_shell(
            title="HR用户管理",
            page_key="users",
            fallback_heading="HR 用户管理",
            fallback_description="创建、启停和维护后台使用账号，支持重置密码与角色控制。",
            current_path=path,
            username=username,
            user_role=user_role,
        )
        if shell:
            status = HTTPStatus.OK if user_role == "admin" else HTTPStatus.FORBIDDEN
            return _html(status, shell)
        if user_role != "admin":
            return _html(HTTPStatus.FORBIDDEN, "<!doctype html><html><body><h1>无权限访问</h1></body></html>")
        return _html(HTTPStatus.OK, "<!doctype html><html><body><h1>HR 用户管理</h1></body></html>")

    if method == "GET" and path == "/api/v2/scorecards":
        return _json(HTTPStatus.OK, {"items": list_jd_scorecards(limit=200)})

    if method == "POST" and path == "/api/v2/scorecards/generate":
        payload = _read_json(handler)
        try:
            scorecard = generate_scorecard_from_jd(
                str(payload.get("jd_text") or ""),
                name=str(payload.get("name") or "").strip() or None,
            )
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.OK, {"scorecard": scorecard})

    if method == "POST" and path == "/api/v2/scorecards":
        payload = _read_json(handler)
        raw_scorecard = payload.get("scorecard")
        if not isinstance(raw_scorecard, dict):
            return _json(HTTPStatus.BAD_REQUEST, {"error": "scorecard 必须是对象"})
        try:
            scorecard_kind = str(payload.get("scorecard_kind") or payload.get("kind") or "").strip() or CUSTOM_SCORING_KIND
            engine_type = str(payload.get("engine_type") or "").strip() or (
                BUILTIN_ENGINE_TYPE if scorecard_kind == BUILTIN_SCORING_KIND else CUSTOM_ENGINE_TYPE
            )
            if scorecard_kind == BUILTIN_SCORING_KIND or engine_type == BUILTIN_ENGINE_TYPE:
                normalized = normalize_builtin_scorecard(raw_scorecard)
            else:
                normalized = normalize_phase2_scorecard(raw_scorecard)
                scorecard_kind = CUSTOM_SCORING_KIND
                engine_type = CUSTOM_ENGINE_TYPE
            item = upsert_jd_scorecard(
                {
                    "id": str(payload.get("id") or "").strip() or None,
                    "name": str(payload.get("name") or normalized.get("name") or "").strip() or normalized.get("name"),
                    "jd_text": normalized.get("jd_text"),
                    "scorecard": normalized,
                    "scorecard_kind": scorecard_kind,
                    "engine_type": engine_type,
                    "schema_version": str(payload.get("schema_version") or normalized.get("schema_version") or "").strip() or normalized.get("schema_version"),
                    "supports_resume_import": bool(payload.get("supports_resume_import"))
                    if payload.get("supports_resume_import") is not None
                    else engine_type == CUSTOM_ENGINE_TYPE,
                    "editable": bool(payload.get("editable", True)),
                    "system_managed": bool(payload.get("system_managed", scorecard_kind == BUILTIN_SCORING_KIND)),
                    "active": bool(payload.get("active", True)),
                    "created_by": str(payload.get("created_by") or "hr_ui").strip() or "hr_ui",
                }
            )
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.OK, {"item": item})

    if method == "GET" and path.startswith("/api/v2/scorecards/"):
        scorecard_id = path.split("/")[-1]
        item = get_jd_scorecard(scorecard_id)
        if not item:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Scorecard not found"})
        return _json(HTTPStatus.OK, {"item": item})

    if method == "GET" and path == "/api/v2/resume-imports":
        return _json(HTTPStatus.OK, {"items": list_resume_import_batches(limit=50)})

    if method == "POST" and path == "/api/v2/resume-imports":
        payload = _read_json(handler)
        scorecard_id = str(payload.get("scorecard_id") or "").strip()
        if not scorecard_id:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "scorecard_id 不能为空"})
        scorecard_record = get_jd_scorecard(scorecard_id)
        if not scorecard_record:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Scorecard not found"})
        if not scorecard_record.get("supports_resume_import"):
            return _json(HTTPStatus.BAD_REQUEST, {"error": "当前评分卡不支持批量导入简历打分"})
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "files 必须是非空数组"})
        try:
            result = ResumeImportService(search_service=SEARCH_SERVICE).import_base64_batch(
                scorecard_id=scorecard_id,
                scorecard=scorecard_record["scorecard"],
                files=files,
                batch_name=str(payload.get("batch_name") or "").strip(),
                created_by=str(payload.get("created_by") or "hr_ui").strip() or "hr_ui",
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, result)

    if method == "GET" and path.startswith("/api/v2/resume-imports/"):
        batch_id = path.split("/")[-1]
        batch = get_resume_import_batch(batch_id)
        if not batch:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Import batch not found"})
        return _json(
            HTTPStatus.OK,
            {
                "batch": batch,
                "results": list_resume_import_results(batch_id),
            },
        )

    if method == "GET" and path == "/api/jobs":
        return _json(HTTPStatus.OK, {"items": list_scoring_targets()})

    if method == "GET" and path == "/api/scoring-targets":
        return _json(
            HTTPStatus.OK,
            {
                "items": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "kind": item["kind"],
                        "schema_version": item["schema_version"],
                        "engine_type": item.get("engine_type"),
                        "supports_resume_import": bool(item.get("supports_resume_import")),
                    }
                    for item in list_scoring_targets()
                ]
            },
        )

    if method == "POST" and path == "/api/extension/candidates/upsert":
        payload = _read_json(handler)
        try:
            result = ExtensionCandidateIngestService().upsert_candidate_page(
                job_id=str(payload.get("job_id") or "").strip(),
                page_url=str(payload.get("page_url") or "").strip(),
                page_title=str(payload.get("page_title") or "").strip(),
                page_text=str(payload.get("page_text") or ""),
                candidate_name=str(payload.get("candidate_name") or "").strip(),
                source=str(payload.get("source") or "boss_extension_v1").strip() or "boss_extension_v1",
                source_candidate_key=str(payload.get("source_candidate_key") or "").strip() or None,
                external_id=str(payload.get("external_id") or "").strip() or None,
                page_type=str(payload.get("page_type") or "boss_resume_detail").strip() or "boss_resume_detail",
                observed_at=str(payload.get("observed_at") or "").strip() or None,
                context_key=str(payload.get("context_key") or "").strip() or None,
                quick_fit_payload=payload.get("quick_fit_payload") if isinstance(payload.get("quick_fit_payload"), dict) else None,
            )
        except KeyError:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Unknown job_id"})
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, result)

    if method == "GET" and path == "/api/extension/candidates/lookup":
        query = parse_qs(parsed.query or "")
        job_id = str((query.get("job_id") or [""])[0] or "").strip()
        source = str((query.get("source") or ["boss_extension_v1"])[0] or "boss_extension_v1").strip() or "boss_extension_v1"
        external_id = str((query.get("external_id") or [""])[0] or "").strip()
        source_candidate_key = str((query.get("source_candidate_key") or [""])[0] or "").strip()
        if not job_id:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "job_id 不能为空"})
        if not external_id and not source_candidate_key:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "external_id 或 source_candidate_key 至少提供一个"})
        binding = None
        if external_id:
            binding = get_extension_candidate_binding_by_external_id(job_id=job_id, source=source, external_id=external_id)
        if not binding and source_candidate_key:
            binding = get_extension_candidate_binding(job_id=job_id, source=source, source_candidate_key=source_candidate_key)
        if not binding:
            return _json(HTTPStatus.OK, {"found": False})
        state = get_candidate_pipeline_state(str(binding["candidate_id"]))
        return _json(
            HTTPStatus.OK,
            {
                "found": True,
                "candidate_id": binding["candidate_id"],
                "pipeline_state": state,
                "last_scored_at": binding.get("last_scored_at"),
            },
        )

    if method == "POST" and path.startswith("/api/extension/candidates/") and path.endswith("/score"):
        candidate_id = path.split("/")[-2]
        candidate = get_candidate(candidate_id)
        if not candidate:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        payload = _read_json(handler)
        try:
            _force_model_env()
            result = ExtensionCandidateIngestService().score_candidate(
                candidate_id=candidate_id,
                job_id=str(payload.get("job_id") or "").strip(),
                page_url=str(payload.get("page_url") or "").strip(),
                page_title=str(payload.get("page_title") or "").strip(),
                page_text=str(payload.get("page_text") or ""),
                candidate_hint=str(payload.get("candidate_hint") or "").strip(),
                source=str(payload.get("source") or "boss_extension_v1").strip() or "boss_extension_v1",
            )
        except KeyError:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Unknown job_id"})
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, result)

    if method == "POST" and path == "/api/extension/score":
        payload = _read_json(handler)
        try:
            _force_model_env()
            result = ExtensionScoreService().score_candidate_page(
                job_id=str(payload.get("job_id") or "").strip(),
                page_url=str(payload.get("page_url") or "").strip(),
                page_title=str(payload.get("page_title") or "").strip(),
                page_text=str(payload.get("page_text") or ""),
                candidate_hint=str(payload.get("candidate_hint") or "").strip(),
                source=str(payload.get("source") or "boss_extension_v1").strip() or "boss_extension_v1",
            )
        except KeyError:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Unknown job_id"})
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, result)

    if method == "POST" and path == "/api/v3/search/index/upsert":
        payload = _read_json(handler)
        items = payload.get("items")
        if items is not None and not isinstance(items, list):
            return _json(HTTPStatus.BAD_REQUEST, {"error": "items 必须是数组"})
        summary = SEARCH_SERVICE.upsert_profiles(items=items)
        return _json(HTTPStatus.OK, summary)

    if method == "GET" and path == "/api/v3/pipelines":
        return _json(HTTPStatus.OK, {"items": PIPELINE_SERVICE.list_pipelines()})

    if method == "POST" and path == "/api/v3/pipelines":
        payload = _read_json(handler)
        if not get_scoring_target(str(payload.get("job_id") or "")):
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Unknown job_id"})
        try:
            item = PIPELINE_SERVICE.upsert_pipeline(payload)
        except Exception as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.OK, {"pipeline": item})

    if method == "POST" and path == "/api/v3/pipelines/run-due":
        try:
            summary = PIPELINE_SERVICE.run_due_pipelines()
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, summary)

    if method == "GET" and path.startswith("/api/v3/pipelines/") and path.endswith("/runs"):
        pipeline_id = path.split("/")[-2]
        if not get_collection_pipeline(pipeline_id):
            return _json(HTTPStatus.NOT_FOUND, {"error": "Pipeline not found"})
        return _json(HTTPStatus.OK, {"items": list_collection_pipeline_runs(pipeline_id)})

    if method == "POST" and path.startswith("/api/v3/pipelines/") and path.endswith("/run"):
        pipeline_id = path.split("/")[-2]
        try:
            summary = PIPELINE_SERVICE.run_pipeline(pipeline_id, force=True)
        except KeyError:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Pipeline not found"})
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, summary)

    if method == "POST" and path == "/api/v3/search/query":
        payload = _read_json(handler)
        try:
            result = SEARCH_SERVICE.search(
                jd_text=payload.get("jd_text"),
                query_text=payload.get("query_text"),
                filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else {},
                top_k=int(payload.get("top_k", 20)),
                explain=bool(payload.get("explain", False)),
            )
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return _json(HTTPStatus.OK, result)

    if method == "GET" and path.startswith("/api/v3/search/runs/"):
        run_id = path.split("/")[-1]
        try:
            result = SEARCH_SERVICE.get_search_run(run_id)
        except KeyError:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Search run not found"})
        return _json(HTTPStatus.OK, result)

    if method == "GET" and path.startswith("/api/v3/candidates/") and path.endswith("/search-profile"):
        candidate_id = path.split("/")[-2]
        try:
            profile = SEARCH_SERVICE.get_search_profile(candidate_id)
        except KeyError:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Search profile not found"})
        return _json(HTTPStatus.OK, profile)

    if method == "GET" and path == "/api/hr/checklist":
        query = parse_qs(parsed.query or "")
        task_id = (query.get("task_id") or [None])[0]
        if task_id == "":
            task_id = None
        job_id = (query.get("job_id") or [None])[0]
        if job_id == "":
            job_id = None
        date_from = (query.get("date_from") or [None])[0]
        if date_from == "":
            date_from = None
        date_to = (query.get("date_to") or [None])[0]
        if date_to == "":
            date_to = None
        raw_limit = (query.get("limit") or ["300"])[0]
        try:
            limit = max(1, min(int(raw_limit), 1000))
        except ValueError:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid limit"})
        return _json(
            HTTPStatus.OK,
            {
                "jobs": list_scoring_targets(),
                "tasks": list_recent_tasks(limit=100),
                "items": list_hr_checklist_items(
                    task_id=task_id,
                    job_id=job_id,
                    date_from=date_from,
                    date_to=date_to,
                    limit=limit,
                ),
            },
        )

    if method == "GET" and path == "/api/hr/workbench":
        query = parse_qs(parsed.query or "")
        task_id = (query.get("task_id") or [None])[0] or None
        job_id = (query.get("job_id") or [None])[0] or None
        source = (query.get("source") or [None])[0] or None
        keyword = (query.get("keyword") or [None])[0] or None
        stage = (query.get("stage") or [None])[0] or None
        decision = (query.get("decision") or [None])[0] or None
        greet_status = (query.get("greet_status") or [None])[0] or None
        owner = (query.get("owner") or [None])[0] or None
        limit_raw = (query.get("limit") or ["200"])[0]
        try:
            limit = max(1, min(int(limit_raw), 500))
        except ValueError:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid limit"})
        reusable_only = _bool_query_param((query.get("reusable_only") or [None])[0]) is True
        needs_follow_up = _bool_query_param((query.get("needs_follow_up") or [None])[0]) is True
        unreviewed_only = _bool_query_param((query.get("unreviewed_only") or [None])[0]) is True
        do_not_contact = _bool_query_param((query.get("do_not_contact") or [None])[0])
        manual_stage_locked = _bool_query_param((query.get("manual_stage_locked") or [None])[0])
        return _json(
            HTTPStatus.OK,
            {
                "jobs": list_scoring_targets(),
                "tasks": list_recent_tasks(limit=100),
                "stage_options": WORKBENCH_STAGE_OPTIONS,
                "reason_code_options": WORKBENCH_REASON_CODES,
                "final_decision_options": WORKBENCH_FINAL_DECISIONS,
                "items": list_hr_workbench_items(
                    task_id=task_id,
                    job_id=job_id,
                    source=source,
                    keyword=keyword,
                    stage=stage,
                    decision=decision,
                    greet_status=greet_status,
                    owner=owner,
                    reusable_only=reusable_only,
                    do_not_contact=do_not_contact,
                    manual_stage_locked=manual_stage_locked,
                    needs_follow_up=needs_follow_up,
                    unreviewed_only=unreviewed_only,
                    limit=limit,
                ),
            },
        )

    if method == "GET" and path.startswith("/api/hr/workbench/candidates/"):
        candidate_id = path.split("/")[-1]
        payload = get_candidate_workbench(candidate_id)
        if not payload:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        return _json(HTTPStatus.OK, payload)

    if method == "POST" and path == "/api/boss/session/save":
        if not _current_user(handler):
            return _json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录平台"})
        payload = _read_json(handler)
        wait_seconds = payload.get("wait_seconds")
        login_url = payload.get("login_url")
        try:
            summary = save_boss_storage_state(
                wait_seconds=int(wait_seconds) if wait_seconds is not None else None,
                login_url=str(login_url) if login_url else None,
                headless=False,
            )
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        if not summary.get("ok"):
            return _json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": summary.get("message") or "未检测到有效的 BOSS 登录状态，请在打开的干净 BOSS 页面里手动登录后再试",
                    "summary": summary,
                },
            )
        return _json(HTTPStatus.OK, summary)

    if method == "POST" and path == "/api/boss/session/sync":
        payload = _read_json(handler)
        try:
            summary = sync_boss_storage_state(
                cookies=list(payload.get("cookies") or []),
                current_url=str(payload.get("current_url") or ""),
                source=str(payload.get("source") or "chrome_extension"),
                browser=str(payload.get("browser") or "chrome"),
                browser_snapshot=payload.get("browser_snapshot") if isinstance(payload.get("browser_snapshot"), dict) else None,
            )
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        if not summary.get("ok"):
            return _json(HTTPStatus.BAD_REQUEST, {"error": summary.get("message") or "BOSS 会话同步失败", "summary": summary})
        return _json(HTTPStatus.OK, summary)

    if method == "POST" and path == "/api/boss/session/reset":
        if not _current_user(handler):
            return _json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录平台"})
        payload = _read_json(handler)
        login_url = payload.get("login_url")
        try:
            summary = reset_boss_storage_state(
                login_url=str(login_url) if login_url else None,
                headless=False,
            )
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return _json(HTTPStatus.OK, summary)

    if method == "POST" and path == "/api/recommend/run":
        if not _current_user(handler):
            return _json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录平台"})
        payload = _read_json(handler)
        job_id = payload.get("job_id")
        if not get_scoring_target(str(job_id or "")):
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Unknown job_id"})
        precheck_error = _model_precheck_error()
        if precheck_error:
            return _json(HTTPStatus.BAD_REQUEST, {"error": precheck_error})

        _force_model_env()
        try:
            session_summary = save_boss_storage_state(
                wait_seconds=max(1, int(payload.get("wait_seconds", os.getenv("SCREENING_AUTH_SAVE_WAIT_SECONDS", "180")))),
                login_url=payload.get("login_url"),
                headless=False,
            )
        except Exception as exc:
            return _json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        if not session_summary.get("ok"):
            return _json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": session_summary.get("message") or "未检测到有效的 BOSS 登录状态，请先在打开的干净 BOSS 页面里手动登录并保存会话",
                    "session": session_summary,
                },
            )

        task_id = create_task(
            {
                "job_id": job_id,
                "search_mode": "recommend",
                "sort_by": payload.get("sort_by", "active"),
                "max_candidates": max(1, int(payload.get("max_candidates", 50))),
                "max_pages": max(1, int(payload.get("max_pages", 30))),
                "search_config": {},
                "require_hr_confirmation": True,
            }
        )
        orchestrator = ScreeningOrchestrator(search_service=SEARCH_SERVICE)
        try:
            result = orchestrator.run_task(task_id)
        except KeyError:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Task not found"})
        task = get_task(task_id) or {"id": task_id}
        return _json(
            HTTPStatus.OK,
            {
                "task_id": task_id,
                "task": task,
                "session": session_summary,
                "result": result,
            },
        )

    if method == "POST" and path == "/api/tasks":
        payload = _read_json(handler)
        if not get_scoring_target(str(payload.get("job_id") or "")):
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Unknown job_id"})
        payload["search_mode"] = "recommend"
        payload.setdefault("sort_by", "active")
        payload.setdefault("max_pages", 1)
        payload.setdefault("search_config", {})
        task_id = create_task(payload)
        return _json(HTTPStatus.CREATED, {"task_id": task_id})

    if method == "GET" and path.startswith("/api/tasks/") and path.endswith("/candidates"):
        task_id = path.split("/")[-2]
        return _json(HTTPStatus.OK, {"items": list_candidates_for_task(task_id)})

    if method == "GET" and path.startswith("/api/tasks/") and path.endswith("/logs"):
        task_id = path.split("/")[-2]
        return _json(HTTPStatus.OK, {"items": list_logs_for_task(task_id)})

    if method == "POST" and path.startswith("/api/tasks/") and path.endswith("/start"):
        task_id = path.split("/")[-2]
        _force_model_env()
        global ORCHESTRATOR
        if type(getattr(ORCHESTRATOR, "browser_agent", None)).__name__ != "MockBrowserAgent":
            ORCHESTRATOR = ScreeningOrchestrator(search_service=SEARCH_SERVICE)
        try:
            result = ORCHESTRATOR.run_task(task_id)
        except KeyError:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Task not found"})
        return _json(HTTPStatus.OK, result)

    if method == "GET" and path.startswith("/api/tasks/"):
        task_id = path.split("/")[-1]
        task = get_task(task_id)
        if not task:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Task not found"})
        task["require_hr_confirmation"] = bool(task["require_hr_confirmation"])
        return _json(HTTPStatus.OK, {"task": task})

    if method == "GET" and path.startswith("/api/candidates/") and path.endswith("/timeline"):
        candidate_id = path.split("/")[-2]
        candidate = get_candidate(candidate_id)
        if not candidate:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        return _json(HTTPStatus.OK, {"items": list_candidate_timeline(candidate_id)})

    if method == "POST" and path.startswith("/api/candidates/") and path.endswith("/stage"):
        candidate_id = path.split("/")[-2]
        candidate = get_candidate(candidate_id)
        if not candidate:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        payload = _read_json(handler)
        current_stage = str(payload.get("current_stage") or "").strip()
        if current_stage not in WORKBENCH_STAGE_OPTIONS:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid current_stage"})
        reason_code = str(payload.get("reason_code") or "").strip() or None
        if reason_code is not None and reason_code not in WORKBENCH_REASON_CODES:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid reason_code"})
        final_decision = str(payload.get("final_decision") or "").strip() or None
        if final_decision is not None and final_decision not in WORKBENCH_FINAL_DECISIONS:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid final_decision"})
        operator = str(payload.get("operator") or "hr_ui").strip() or "hr_ui"
        review_action = str(payload.get("review_action") or "").strip() or None
        if review_action and review_action not in {item.value for item in ReviewAction}:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid review_action"})
        state = save_candidate_stage_action(
            candidate_id,
            operator=operator,
            current_stage=current_stage,
            reason_code=reason_code,
            reason_notes=str(payload.get("reason_notes") or "").strip() or None,
            final_decision=final_decision,
            owner=str(payload.get("owner") or "").strip() or None,
            reusable_flag=bool(payload.get("reusable_flag")) if payload.get("reusable_flag") is not None else None,
            do_not_contact=bool(payload.get("do_not_contact")) if payload.get("do_not_contact") is not None else None,
            talent_pool_status=str(payload.get("talent_pool_status") or "").strip() or None,
            last_contacted_at=str(payload.get("last_contacted_at") or "").strip() or None,
            last_contact_result=str(payload.get("last_contact_result") or "").strip() or None,
            next_follow_up_at=str(payload.get("next_follow_up_at") or "").strip() or None,
        )
        review_id = None
        if review_action:
            review_id = add_review_action(
                candidate_id,
                operator,
                review_action,
                str(payload.get("reason_notes") or "").strip() or None,
                final_decision,
            )
            add_candidate_timeline_event(
                candidate_id,
                "review_action",
                operator,
                {"action": review_action, "final_decision": final_decision},
            )
        return _json(HTTPStatus.OK, {"ok": True, "state": state, "review_id": review_id})

    if method == "POST" and path.startswith("/api/candidates/") and path.endswith("/tags"):
        candidate_id = path.split("/")[-2]
        candidate = get_candidate(candidate_id)
        if not candidate:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        payload = _read_json(handler)
        try:
            tag_id = add_candidate_tag(
                candidate_id,
                str(payload.get("tag") or ""),
                str(payload.get("created_by") or "hr_ui").strip() or "hr_ui",
                tag_type=str(payload.get("tag_type") or "manual"),
            )
        except ValueError as exc:
            return _json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        add_candidate_timeline_event(
            candidate_id,
            "tag_added",
            str(payload.get("created_by") or "hr_ui").strip() or "hr_ui",
            {"tag": str(payload.get("tag") or "").strip(), "tag_type": str(payload.get("tag_type") or "manual")},
        )
        return _json(HTTPStatus.CREATED, {"tag_id": tag_id})

    if method == "POST" and path.startswith("/api/candidates/") and path.endswith("/follow-up"):
        candidate_id = path.split("/")[-2]
        candidate = get_candidate(candidate_id)
        if not candidate:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        payload = _read_json(handler)
        state = save_candidate_follow_up(
            candidate_id,
            operator=str(payload.get("operator") or "hr_ui").strip() or "hr_ui",
            next_follow_up_at=str(payload.get("next_follow_up_at") or "").strip() or None,
            last_contact_result=str(payload.get("last_contact_result") or "").strip() or None,
            comment=str(payload.get("comment") or "").strip() or None,
        )
        return _json(HTTPStatus.OK, {"ok": True, "state": state})

    if method == "GET" and path.startswith("/api/candidates/"):
        if path.endswith("/screenshot"):
            candidate_id = path.split("/")[-2]
            candidate = get_candidate(candidate_id)
            if not candidate:
                return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
            snapshot = candidate.get("snapshot") or {}
            screenshot_path = snapshot.get("screenshot_path")
            if not screenshot_path:
                return _json(HTTPStatus.NOT_FOUND, {"error": "Screenshot not found"})
            screenshot_file = Path(screenshot_path)
            if not screenshot_file.exists():
                return _json(HTTPStatus.NOT_FOUND, {"error": f"Screenshot file missing: {screenshot_path}"})
            mime, _ = mimetypes.guess_type(str(screenshot_file))
            return _body(HTTPStatus.OK, screenshot_file.read_bytes(), mime or "application/octet-stream")

        candidate_id = path.split("/")[-1]
        candidate = get_candidate(candidate_id)
        if not candidate:
            return _json(HTTPStatus.NOT_FOUND, {"error": "Candidate not found"})
        return _json(HTTPStatus.OK, candidate)

    if method == "GET" and path == "/hr/checklist":
        username = _current_user(handler) or AUTH_USERNAME
        return _html(
            HTTPStatus.OK,
            """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HR 简历评分清单</title>
  <style>
    :root {
      --boss-blue: #00bebd;
      --boss-deep: #0479ff;
      --bg: #f3f8ff;
      --card: #ffffff;
      --text: #1d2433;
      --muted: #5d6785;
      --line: #e5e8f0;
      --ok: #0e9f6e;
      --warn: #d97706;
      --bad: #dc2626;
      --brand: #0479ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: radial-gradient(1100px 360px at -10% -10%, #d8fffb 0%, transparent 60%),
                  radial-gradient(1000px 320px at 100% -20%, #dce8ff 0%, transparent 60%),
                  var(--bg);
      color: var(--text);
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 2;
      background: linear-gradient(110deg, var(--boss-deep), var(--boss-blue));
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 18px;
    }
    .topbar .brand { font-weight: 700; }
    .topbar .nav {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .topbar .nav-group {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.12);
    }
    .topbar .nav-label {
      font-size: 12px;
      color: rgba(255,255,255,.78);
    }
    .topbar a, .topbar button {
      color: #fff;
      text-decoration: none;
      background: transparent;
      border: 1px solid rgba(255,255,255,.45);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      cursor: pointer;
    }
    .wrap { max-width: 1400px; margin: 0 auto; padding: 20px; }
    h1 { margin: 0 0 16px; font-size: 24px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px; }
    .toolbar select, .toolbar button, .toolbar input {
      border: 1px solid var(--line); border-radius: 8px; height: 36px; padding: 0 10px; background: #fff; color: var(--text);
    }
    .toolbar button { cursor: pointer; background: var(--brand); color: #fff; border-color: var(--brand); }
    .meta { margin: 10px 0 0; color: var(--muted); font-size: 13px; }
    .card { margin-top: 14px; background: var(--card); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--line); padding: 10px; text-align: left; font-size: 13px; vertical-align: top; }
    th { background: #f2f4fa; font-weight: 600; position: sticky; top: 0; z-index: 1; }
    .tag { display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; }
    .decision-recommend { color: #fff; background: var(--ok); }
    .decision-review { color: #fff; background: var(--warn); }
    .decision-reject { color: #fff; background: var(--bad); }
    .review-done { color: #fff; background: var(--ok); }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    .review-btn {
      cursor: pointer;
      border: 1px solid var(--brand);
      color: var(--brand);
      background: #fff;
      border-radius: 8px;
      height: 30px;
      padding: 0 10px;
      font-size: 12px;
    }
    .review-btn[disabled] { opacity: 0.6; cursor: not-allowed; }
    a { color: var(--brand); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .error { color: var(--bad); font-size: 12px; max-width: 280px; white-space: pre-wrap; }
    .empty { padding: 20px; color: var(--muted); }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">HRClaw · HR Checklist</div>
    <div class="nav">
      <span>用户：__USERNAME__</span>
      <div class="nav-group">
        <span class="nav-label">流程</span>
        <a href="/hr/tasks">任务执行</a>
        <a href="/hr/workbench">推荐处理台</a>
      </div>
      <div class="nav-group">
        <span class="nav-label">搜索</span>
        <a href="/hr/search">高级搜索</a>
      </div>
      <div class="nav-group">
        <span class="nav-label">当前页</span>
        <a href="/hr/checklist">Checklist</a>
      </div>
      <button id="logoutBtn" type="button">退出</button>
    </div>
  </div>
  <div class="wrap">
    <h1>HR 简历评分清单</h1>
    <div class="toolbar">
      <select id="taskId">
        <option value="">全部任务</option>
      </select>
      <select id="jobId">
        <option value="">全部岗位</option>
      </select>
      <input id="dateFrom" type="date" />
      <input id="dateTo" type="date" />
      <input id="limit" type="number" min="1" max="1000" value="300" />
      <button id="refreshBtn">刷新</button>
      <span class="meta" id="meta"></span>
    </div>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>任务</th>
            <th>Token消耗</th>
            <th>候选人</th>
            <th>综合分</th>
            <th>系统决策</th>
            <th>打招呼</th>
            <th>HR复核</th>
            <th>经验/学历/城市</th>
            <th>岗位信息/搜索条件</th>
            <th>模型提取</th>
            <th>证据</th>
          </tr>
        </thead>
        <tbody id="rows">
          <tr><td class="empty" colspan="11">加载中...</td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <script>
    const taskSelect = document.getElementById("taskId");
    const jobSelect = document.getElementById("jobId");
    const dateFromInput = document.getElementById("dateFrom");
    const dateToInput = document.getElementById("dateTo");
    const limitInput = document.getElementById("limit");
    const refreshBtn = document.getElementById("refreshBtn");
    const rows = document.getElementById("rows");
    const meta = document.getElementById("meta");

    function esc(value) {
      if (value === null || value === undefined) return "";
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function tagDecision(decision) {
      const raw = String(decision || "unknown");
      const safe = esc(raw);
      const cls = `decision-${safe}`;
      const labels = {
        recommend: "建议沟通",
        review: "继续复核",
        reject: "暂不沟通",
      };
      return `<span class="tag ${cls}">${esc(labels[raw] || raw)}</span>`;
    }

    function fmtTime(value) {
      return value ? esc(value) : "-";
    }

    function reviewCell(item) {
      if (item.review_action || item.final_decision) {
        return `<span class="tag review-done">复核完成</span><br/><span>${esc(item.reviewer || "")}</span>`;
      }
      return `<button class="review-btn" data-candidate-id="${esc(item.candidate_id)}">是否复核</button>`;
    }

    function tokenNumber(value) {
      const n = Number(value);
      if (!Number.isFinite(n) || n < 0) return 0;
      return Math.round(n);
    }

    function tokenUsageCell(tokenUsage) {
      const usage = tokenUsage || {};
      const total = tokenNumber(usage.total_tokens);
      const prompt = tokenNumber(usage.prompt_tokens);
      const completion = tokenNumber(usage.completion_tokens);
      const calls = tokenNumber(usage.calls);
      if (total === 0 && prompt === 0 && completion === 0 && calls === 0) return "-";
      return `总: ${total}<br/>输: ${prompt} / 出: ${completion}<br/>调用: ${calls}`;
    }

    async function markReviewed(candidateId) {
      const res = await fetch(`/api/candidates/${encodeURIComponent(candidateId)}/review`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          reviewer: "hr_ui",
          action: "approve",
          comment: "HR清单页面复核完成",
          final_decision: "reviewed_completed"
        })
      });
      if (!res.ok) {
        let message = `复核失败(${res.status})`;
        try {
          const payload = await res.json();
          if (payload && payload.error) message = payload.error;
        } catch (_) {}
        throw new Error(message);
      }
    }

    async function loadChecklist() {
      const taskId = taskSelect.value;
      const jobId = jobSelect.value;
      const dateFrom = dateFromInput.value;
      const dateTo = dateToInput.value;
      const limit = Number(limitInput.value || 300);
      const params = new URLSearchParams();
      if (taskId) params.set("task_id", taskId);
      if (jobId) params.set("job_id", jobId);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      params.set("limit", String(limit));
      const res = await fetch(`/api/hr/checklist?${params.toString()}`);
      const data = await res.json();
      const jobs = data.jobs || [];
      const tasks = data.tasks || [];
      const items = data.items || [];
      const totalTaskTokens = tasks.reduce((sum, task) => sum + tokenNumber((task.token_usage || {}).total_tokens), 0);

      const oldTaskId = taskId;
      const oldJobId = jobId;
      taskSelect.innerHTML = '<option value="">全部任务</option>' + tasks.map(t => (
        `<option value="${esc(t.id)}">${esc(t.id)} | ${esc(t.job_id)} | ${esc(t.status)}</option>`
      )).join("");
      taskSelect.value = oldTaskId;
      jobSelect.innerHTML = '<option value="">全部岗位</option>' + jobs.map(j => (
        `<option value="${esc(j.id)}">${esc(j.name)} (${esc(j.id)})</option>`
      )).join("");
      jobSelect.value = oldJobId;

      meta.textContent = `任务数: ${tasks.length}，候选人数: ${items.length}，累计Token: ${totalTaskTokens}`;
      if (!items.length) {
        rows.innerHTML = '<tr><td class="empty" colspan="11">暂无数据</td></tr>';
        return;
      }

      rows.innerHTML = items.map(item => {
        const modelExtraction = item.gpt_extraction_used === true ? "成功" : (item.gpt_extraction_used === false ? "回退" : "未知");
        const screenshotLink = item.screenshot_path
          ? `<a target="_blank" href="/api/candidates/${esc(item.candidate_id)}/screenshot">简历截图</a>`
          : "-";
        const detailLink = `<a target="_blank" href="/api/candidates/${esc(item.candidate_id)}">详情JSON</a>`;
        const searchConfig = item.search_config || {};
        const keyword = searchConfig.keyword || "-";
        const city = searchConfig.city || "-";
        return `
          <tr>
            <td class="mono">
              ${esc(item.task_id)}<br/>
              <span>状态: ${esc(item.task_status)}</span><br/>
              <span>开始: ${fmtTime(item.task_started_at)}</span><br/>
              <span>结束: ${fmtTime(item.task_finished_at)}</span>
            </td>
            <td class="mono">${tokenUsageCell(item.task_token_usage)}</td>
            <td>${esc(item.name || "-")}<br/><span class="mono">${esc(item.external_id || "-")}</span></td>
            <td>${item.total_score === null || item.total_score === undefined ? "-" : Number(item.total_score).toFixed(2)}</td>
            <td>${tagDecision(item.decision)}</td>
            <td>${esc(item.greet_status || "-")}</td>
            <td>${reviewCell(item)}</td>
            <td>${esc(item.years_experience || "-")} 年 / ${esc(item.education_level || "-")} / ${esc(item.location || "-")}</td>
            <td>
              岗位: ${esc(item.job_name || item.job_id || "-")}<br/>
              关键词: ${esc(keyword)}<br/>
              城市: ${esc(city)}
            </td>
            <td>${esc(modelExtraction)}${item.gpt_extraction_error ? `<div class="error">${esc(item.gpt_extraction_error)}</div>` : ""}</td>
            <td>${screenshotLink} | ${detailLink}</td>
          </tr>
        `;
      }).join("");
    }

    refreshBtn.addEventListener("click", loadChecklist);
    document.getElementById("logoutBtn").addEventListener("click", async () => {
      try {
        await fetch("/api/logout", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: "{}"
        });
      } catch (_) {}
      window.location.href = "/login";
    });
    taskSelect.addEventListener("change", loadChecklist);
    jobSelect.addEventListener("change", loadChecklist);
    dateFromInput.addEventListener("change", loadChecklist);
    dateToInput.addEventListener("change", loadChecklist);
    rows.addEventListener("click", async (event) => {
      const target = event.target.closest("button[data-candidate-id]");
      if (!target) return;
      const candidateId = target.getAttribute("data-candidate-id");
      if (!candidateId) return;
      target.disabled = true;
      target.textContent = "复核中...";
      try {
        await markReviewed(candidateId);
        await loadChecklist();
      } catch (err) {
        target.disabled = false;
        target.textContent = "是否复核";
        alert(`复核失败: ${err.message}`);
      }
    });
    loadChecklist().catch((err) => {
      rows.innerHTML = `<tr><td class="empty" colspan="11">加载失败: ${esc(err.message)}</td></tr>`;
    });
  </script>
</body>
</html>""".replace("__USERNAME__", username),
        )

    if method == "POST" and path.startswith("/api/candidates/") and path.endswith("/review"):
        candidate_id = path.split("/")[-2]
        payload = _read_json(handler)
        action = payload.get("action")
        if action not in {item.value for item in ReviewAction}:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid review action"})
        review_id = add_review_action(
            candidate_id,
            payload["reviewer"],
            action,
            payload.get("comment"),
            payload.get("final_decision"),
        )
        add_candidate_timeline_event(
            candidate_id,
            "review_action",
            str(payload.get("reviewer") or "hr_ui"),
            {
                "action": action,
                "comment": payload.get("comment"),
                "final_decision": payload.get("final_decision"),
            },
        )
        return _json(HTTPStatus.CREATED, {"review_id": review_id})

    if method == "POST" and path.startswith("/api/candidates/") and path.endswith("/confirm-action"):
        candidate_id = path.split("/")[-2]
        payload = _read_json(handler)
        action = payload.get("action")
        if action not in {item.value for item in ConfirmableAction}:
            return _json(HTTPStatus.BAD_REQUEST, {"error": "Invalid confirmable action"})
        review_id = add_review_action(
            candidate_id,
            payload["confirmed_by"],
            action,
            payload.get("comment"),
            payload.get("final_decision", "confirmed"),
        )
        add_candidate_timeline_event(
            candidate_id,
            "confirm_action",
            str(payload.get("confirmed_by") or "hr_ui"),
            {
                "action": action,
                "comment": payload.get("comment"),
                "final_decision": payload.get("final_decision", "confirmed"),
            },
        )
        return _json(HTTPStatus.CREATED, {"confirmation_id": review_id})

    return _json(HTTPStatus.NOT_FOUND, {"error": f"No route for {method} {path}"})
