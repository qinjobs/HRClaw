from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .config import load_local_env

DEFAULT_VALIDATE_URL = "https://www.zhipin.com/web/chat/index"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def _storage_state_path() -> Path:
    configured_storage_state = os.getenv("SCREENING_BROWSER_STORAGE_STATE_PATH")
    if configured_storage_state:
        return Path(configured_storage_state)
    return Path(__file__).resolve().parents[2] / "data" / "auth" / "boss_storage_state.json"


def _session_meta_path() -> Path:
    return _storage_state_path().with_name("boss_session_meta.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _same_site_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "no_restriction", "unspecified"}:
        return "None" if normalized == "no_restriction" else "Lax"
    if normalized == "strict":
        return "Strict"
    return "Lax"


def _normalize_browser_cookie(cookie: dict[str, Any]) -> dict[str, Any] | None:
    name = str(cookie.get("name") or "").strip()
    domain = str(cookie.get("domain") or "").strip()
    path = str(cookie.get("path") or "/").strip() or "/"
    if not name or not domain:
        return None
    expiration = cookie.get("expirationDate")
    session_cookie = bool(cookie.get("session"))
    expires = -1
    if not session_cookie and expiration is not None:
        try:
            expires = int(float(expiration))
        except Exception:
            expires = -1
    return {
        "name": name,
        "value": str(cookie.get("value") or ""),
        "domain": domain,
        "path": path,
        "expires": expires,
        "httpOnly": bool(cookie.get("httpOnly")),
        "secure": bool(cookie.get("secure")),
        "sameSite": _same_site_label(cookie.get("sameSite")),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def _read_storage_state() -> dict[str, Any]:
    path = _storage_state_path()
    if not path.exists():
        return {}
    return _read_json(path)


def _write_storage_state(payload: dict[str, Any]) -> None:
    _write_json(_storage_state_path(), payload)


def _read_session_meta() -> dict[str, Any]:
    path = _session_meta_path()
    if not path.exists():
        return {}
    return _read_json(path)


def _write_session_meta(payload: dict[str, Any]) -> None:
    _write_json(_session_meta_path(), payload)


def _build_requests_session(cookies: list[dict[str, Any]]) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.zhipin.com/",
        }
    )
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        domain = str(cookie.get("domain") or "").strip()
        if not name or not domain:
            continue
        session.cookies.set(
            name,
            str(cookie.get("value") or ""),
            domain=domain,
            path=str(cookie.get("path") or "/"),
        )
    return session


def _validate_recruiter_html(*, current_url: str, body_text: str) -> tuple[bool, str]:
    if "/web/user" in current_url:
        return False, "on_login_page"
    if "当前登录状态已失效" in body_text:
        return False, "session_invalid"
    if "验证码登录/注册" in body_text or "扫码登录" in body_text or "登录/注册" in body_text:
        return False, "on_login_form"

    recruiter_markers = ("职位管理", "推荐牛人", "沟通", "牛人管理", "面试", "人才库")
    hit_count = sum(1 for marker in recruiter_markers if marker in body_text)
    if hit_count >= 2:
        return True, "recruiter_ui_detected"
    if hit_count >= 1 and any(token in current_url for token in ("/web/chat/", "/web/geek/", "/web/boss/", "/web/recommend/")):
        return True, "recruiter_page_detected"
    return False, "recruiter_ui_not_detected"


def _validate_browser_snapshot(meta: dict[str, Any]) -> tuple[bool, str] | None:
    snapshot = meta.get("browser_snapshot")
    if not isinstance(snapshot, dict):
        return None
    current_url = str(snapshot.get("current_url") or meta.get("current_url") or "")
    body_text = str(snapshot.get("body_text") or "")
    if not current_url and not body_text:
        return None
    login_detected, reason = _validate_recruiter_html(current_url=current_url, body_text=body_text)
    if login_detected:
        return True, reason
    # Real browser DOM on recruiter pages is more reliable than backend HTTP shell responses.
    if body_text and not any(token in body_text for token in ("扫码登录", "登录/注册", "验证码登录/注册", "当前登录状态已失效")):
        if any(token in current_url for token in ("/web/chat/", "/web/geek/", "/web/boss/", "/web/recommend/")):
            return True, "browser_snapshot_recruiter_page"
    return False, reason


def _validate_saved_session() -> dict[str, Any]:
    storage_state = _read_storage_state()
    cookies = list(storage_state.get("cookies") or [])
    meta = _read_session_meta()
    if not cookies:
        return {
            "ok": False,
            "login_detected": False,
            "manual_login_required": True,
            "reason": "session_not_synced",
            "current_url": str(meta.get("current_url") or ""),
            "message": "尚未检测到 Chrome 已同步的 BOSS 会话。请先在已安装插件的 Chrome 中手动登录 BOSS，并刷新一次 BOSS 页面后再回来检查。",
        }

    snapshot_validation = _validate_browser_snapshot(meta)
    if snapshot_validation is not None:
        login_detected, reason = snapshot_validation
        current_url = str((meta.get("browser_snapshot") or {}).get("current_url") or meta.get("current_url") or "")
        next_meta = dict(meta)
        next_meta.update(
            {
                "last_validated_at": _utc_now_iso(),
                "last_validation_url": current_url,
                "last_validation_reason": reason,
                "last_login_detected": login_detected,
            }
        )
        _write_session_meta(next_meta)
        if login_detected:
            return {
                "ok": True,
                "login_detected": True,
                "manual_login_required": False,
                "reason": reason,
                "current_url": current_url,
                "message": "已根据 Chrome 当前页面状态检测到有效的 BOSS 招聘端登录会话，并完成本地会话保存。",
            }

    validate_url = os.getenv("SCREENING_AUTH_VALIDATE_URL", DEFAULT_VALIDATE_URL)
    session = _build_requests_session(cookies)
    try:
        response = session.get(validate_url, timeout=15, allow_redirects=True)
        current_url = str(response.url or "")
        body_text = response.text[:8000]
    except Exception as exc:
        current_url = str(meta.get("current_url") or "")
        return {
            "ok": False,
            "login_detected": False,
            "manual_login_required": True,
            "reason": "validation_request_failed",
            "current_url": current_url,
            "message": f"BOSS 会话校验请求失败：{exc}",
        }

    login_detected, reason = _validate_recruiter_html(current_url=current_url, body_text=body_text)
    next_meta = dict(meta)
    next_meta.update(
        {
            "last_validated_at": _utc_now_iso(),
            "last_validation_url": current_url,
            "last_validation_reason": reason,
            "last_login_detected": login_detected,
        }
    )
    _write_session_meta(next_meta)
    if not login_detected:
        return {
            "ok": False,
            "login_detected": False,
            "manual_login_required": True,
            "reason": reason,
            "current_url": current_url,
            "message": "未检测到有效的 BOSS 招聘端登录状态。请先在已安装插件的 Chrome 中手动登录 BOSS，并刷新一次 BOSS 页面后再回来检查。",
        }

    return {
        "ok": True,
        "login_detected": True,
        "manual_login_required": False,
        "reason": reason,
        "current_url": current_url,
        "message": "已检测到 Chrome 当前同步的有效 BOSS 招聘端会话，并完成本地会话保存。",
    }


def sync_boss_storage_state(
    *,
    cookies: list[dict[str, Any]],
    current_url: str | None = None,
    source: str = "chrome_extension",
    browser: str = "chrome",
    browser_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    load_local_env()
    normalized_cookies = [cookie for cookie in (_normalize_browser_cookie(item) for item in cookies or []) if cookie]
    if not normalized_cookies:
        return {
            "ok": False,
            "cookie_count": 0,
            "message": "未收到可用的 BOSS 浏览器 Cookie。",
        }

    _write_storage_state({"cookies": normalized_cookies, "origins": []})
    _write_session_meta(
        {
            "source": source,
            "browser": browser,
            "current_url": str(current_url or ""),
            "cookie_count": len(normalized_cookies),
            "synced_at": _utc_now_iso(),
            "browser_snapshot": browser_snapshot or {},
        }
    )
    return {
        "ok": True,
        "cookie_count": len(normalized_cookies),
        "current_url": str(current_url or ""),
        "source": source,
        "browser": browser,
        "storage_state_path": str(_storage_state_path()),
        "message": "已从当前 Chrome 会话同步 BOSS Cookie 到本地筛选系统。",
    }


def reset_boss_storage_state(
    *,
    login_url: str | None = None,
    headless: bool = False,
) -> dict[str, Any]:
    del login_url
    del headless
    load_local_env()

    cleared_storage = False
    for path in (_storage_state_path(), _session_meta_path()):
        if path.exists():
            path.unlink()
            cleared_storage = True

    return {
        "ok": True,
        "login_detected": False,
        "manual_login_required": True,
        "session_cleared": cleared_storage,
        "reason": "session_reset",
        "storage_state_path": str(_storage_state_path()),
        "message": "已清空本地保存的 BOSS 会话。请在已安装插件的 Chrome 中手动登录 BOSS，并刷新一次 BOSS 页面让插件重新同步会话。",
    }


def save_boss_storage_state(
    *,
    wait_seconds: int | None = None,
    login_url: str | None = None,
    headless: bool = False,
) -> dict[str, Any]:
    del wait_seconds
    del login_url
    del headless
    load_local_env()

    summary = _validate_saved_session()
    summary.setdefault("storage_state_path", str(_storage_state_path()))
    meta = _read_session_meta()
    if meta:
        summary["source"] = meta.get("source")
        summary["browser"] = meta.get("browser")
        summary["synced_at"] = meta.get("synced_at")
    return summary
