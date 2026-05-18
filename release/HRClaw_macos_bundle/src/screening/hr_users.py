from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from typing import Any

from .db import connect


USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")
PASSWORD_MIN_LENGTH = 3
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120_000
USER_ROLES = {"admin", "hr"}


def _normalize_username(value: str) -> str:
    username = str(value or "").strip()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("用户名仅支持 3-64 位字母、数字、点、下划线、中划线或 @")
    return username


def _normalize_role(value: str | None) -> str:
    role = str(value or "hr").strip().lower() or "hr"
    if role not in USER_ROLES:
        raise ValueError("用户角色仅支持 admin 或 hr")
    return role


def _normalize_display_name(value: str | None, *, fallback: str) -> str:
    display_name = str(value or "").strip()
    if not display_name:
        display_name = fallback
    if len(display_name) > 40:
        raise ValueError("显示名称不能超过 40 个字符")
    return display_name


def _normalize_notes(value: str | None) -> str:
    notes = str(value or "").strip()
    if len(notes) > 500:
        raise ValueError("备注不能超过 500 个字符")
    return notes


def _normalize_password(value: str) -> str:
    password = str(value or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"密码长度不能少于 {PASSWORD_MIN_LENGTH} 位")
    return password


def hash_password(password: str) -> str:
    normalized = _normalize_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        normalized.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, expected = str(password_hash or "").split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_text)
    except Exception:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(digest.hex(), expected)


def _user_from_row(row, *, include_secret: bool = False) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    payload = {
        "id": str(item.get("id") or ""),
        "username": str(item.get("username") or ""),
        "display_name": str(item.get("display_name") or item.get("username") or ""),
        "role": str(item.get("role") or "hr"),
        "active": bool(item.get("active")),
        "notes": str(item.get("notes") or ""),
        "last_login_at": item.get("last_login_at"),
        "system_managed": bool(item.get("system_managed")),
        "created_by": str(item.get("created_by") or ""),
        "updated_by": str(item.get("updated_by") or ""),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }
    if include_secret:
        payload["password_hash"] = str(item.get("password_hash") or "")
    return payload


def _count_active_admins(conn, *, exclude_user_id: str | None = None) -> int:
    if exclude_user_id:
        row = conn.execute(
            """
            select count(*) as count
            from hr_users
            where role = 'admin' and active = 1 and id != ?
            """,
            (exclude_user_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "select count(*) as count from hr_users where role = 'admin' and active = 1"
        ).fetchone()
    return int((row or {})["count"] or 0)


def ensure_default_admin_user(username: str, password: str) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    normalized_password = str(password or "")
    if not normalized_password:
        raise ValueError("默认管理员密码不能为空")

    with connect() as conn:
        existing = conn.execute(
            "select * from hr_users where lower(username) = lower(?)",
            (normalized_username,),
        ).fetchone()
        if existing:
            row = dict(existing)
            if str(row.get("role") or "") != "admin" or not bool(row.get("active")) or not bool(row.get("system_managed")):
                conn.execute(
                    """
                    update hr_users
                    set display_name = coalesce(nullif(display_name, ''), username),
                        role = 'admin',
                        active = 1,
                        system_managed = 1,
                        updated_by = 'system',
                        updated_at = current_timestamp
                    where id = ?
                    """,
                    (str(row.get("id") or ""),),
                )
                existing = conn.execute("select * from hr_users where id = ?", (str(row.get("id") or ""),)).fetchone()
            return _user_from_row(existing) or {}

        user_id = str(uuid.uuid4())
        conn.execute(
            """
            insert into hr_users (
                id, username, display_name, password_hash, role, active, notes,
                system_managed, created_by, updated_by
            ) values (?, ?, ?, ?, 'admin', 1, '', 1, 'system', 'system')
            """,
            (
                user_id,
                normalized_username,
                normalized_username,
                hash_password(normalized_password),
            ),
        )
        created = conn.execute("select * from hr_users where id = ?", (user_id,)).fetchone()
        return _user_from_row(created) or {}


def list_hr_users() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from hr_users
            order by
                case role when 'admin' then 0 else 1 end,
                active desc,
                created_at asc
            """
        ).fetchall()
    return [_user_from_row(row) for row in rows if _user_from_row(row) is not None]


def get_hr_user_by_id(user_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("select * from hr_users where id = ?", (str(user_id or ""),)).fetchone()
    return _user_from_row(row, include_secret=include_secret)


def get_hr_user_by_username(username: str, *, include_secret: bool = False) -> dict[str, Any] | None:
    if not str(username or "").strip():
        return None
    with connect() as conn:
        row = conn.execute(
            "select * from hr_users where lower(username) = lower(?)",
            (str(username).strip(),),
        ).fetchone()
    return _user_from_row(row, include_secret=include_secret)


def create_hr_user(
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    role: str = "hr",
    active: bool = True,
    notes: str | None = None,
    operator: str = "admin",
) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    normalized_role = _normalize_role(role)
    normalized_display_name = _normalize_display_name(display_name, fallback=normalized_username)
    normalized_notes = _normalize_notes(notes)
    password_hash = hash_password(password)

    with connect() as conn:
        existing = conn.execute(
            "select id from hr_users where lower(username) = lower(?)",
            (normalized_username,),
        ).fetchone()
        if existing:
            raise ValueError("用户名已存在")
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            insert into hr_users (
                id, username, display_name, password_hash, role, active, notes,
                system_managed, created_by, updated_by
            ) values (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                user_id,
                normalized_username,
                normalized_display_name,
                password_hash,
                normalized_role,
                1 if active else 0,
                normalized_notes,
                str(operator or "admin"),
                str(operator or "admin"),
            ),
        )
        row = conn.execute("select * from hr_users where id = ?", (user_id,)).fetchone()
    return _user_from_row(row) or {}


def update_hr_user(
    *,
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    notes: str | None = None,
    operator: str = "admin",
) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("select * from hr_users where id = ?", (str(user_id or ""),)).fetchone()
        if row is None:
            raise LookupError("用户不存在")
        existing = dict(row)
        next_role = _normalize_role(role or existing.get("role") or "hr")
        next_active = bool(existing.get("active")) if active is None else bool(active)
        next_display_name = _normalize_display_name(display_name, fallback=str(existing.get("username") or ""))
        next_notes = _normalize_notes(notes if notes is not None else existing.get("notes"))

        if bool(existing.get("system_managed")) and (next_role != "admin" or not next_active):
            raise ValueError("系统管理员账号不能被停用或降级")

        if str(existing.get("role") or "") == "admin" and (next_role != "admin" or not next_active):
            if _count_active_admins(conn, exclude_user_id=str(existing.get("id") or "")) <= 0:
                raise ValueError("至少保留 1 个启用中的管理员账号")

        conn.execute(
            """
            update hr_users
            set display_name = ?,
                role = ?,
                active = ?,
                notes = ?,
                updated_by = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (
                next_display_name,
                next_role,
                1 if next_active else 0,
                next_notes,
                str(operator or "admin"),
                str(existing.get("id") or ""),
            ),
        )
        updated = conn.execute("select * from hr_users where id = ?", (str(existing.get("id") or ""),)).fetchone()
    return _user_from_row(updated) or {}


def reset_hr_user_password(*, user_id: str, password: str, operator: str = "admin") -> dict[str, Any]:
    password_hash = hash_password(password)
    with connect() as conn:
        row = conn.execute("select * from hr_users where id = ?", (str(user_id or ""),)).fetchone()
        if row is None:
            raise LookupError("用户不存在")
        conn.execute(
            """
            update hr_users
            set password_hash = ?,
                updated_by = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (
                password_hash,
                str(operator or "admin"),
                str(dict(row).get("id") or ""),
            ),
        )
        updated = conn.execute("select * from hr_users where id = ?", (str(dict(row).get("id") or ""),)).fetchone()
    return _user_from_row(updated) or {}


def record_hr_user_login(user_id: str) -> None:
    if not str(user_id or "").strip():
        return
    with connect() as conn:
        conn.execute(
            """
            update hr_users
            set last_login_at = current_timestamp,
                updated_at = current_timestamp
            where id = ?
            """,
            (str(user_id or "").strip(),),
        )
