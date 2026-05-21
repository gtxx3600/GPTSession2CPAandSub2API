from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SUPPORTED_FORMATS = ("cockpit", "cpa", "sub2api", "9router", "axonhub")
AXONHUB_PLACEHOLDER_REFRESH_TOKEN = "__missing_refresh_token__"


@dataclass(frozen=True)
class FoundSession:
    value: dict[str, Any]
    source_name: str = "pasted-json"
    path: str = "$"


@dataclass(frozen=True)
class SkippedItem:
    source_name: str
    path: str
    reason: str


@dataclass(frozen=True)
class ConvertedSession:
    source_name: str
    source_path: str | None
    email: str | None
    name: str
    expires_at: str | None
    cpa: dict[str, Any]
    cockpit: dict[str, Any]
    sub2api_account: dict[str, Any]
    nine_router: dict[str, Any]
    axonhub: dict[str, Any]


@dataclass(frozen=True)
class ConversionResult:
    sessions: list[FoundSession]
    converted: list[ConvertedSession]
    skipped: list[SkippedItem]
    output: Any


def is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_path(record: dict[str, Any], *keys: str) -> Any:
    current: Any = record
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def access_token_from(record: dict[str, Any]) -> str | None:
    return first_non_empty(
        record.get("accessToken"),
        record.get("access_token"),
        get_path(record, "token", "accessToken"),
        get_path(record, "token", "access_token"),
        get_path(record, "tokens", "access_token"),
        get_path(record, "credentials", "accessToken"),
        get_path(record, "credentials", "access_token"),
    )


def refresh_token_from(record: dict[str, Any]) -> str | None:
    return first_non_empty(
        record.get("refreshToken"),
        record.get("refresh_token"),
        get_path(record, "token", "refreshToken"),
        get_path(record, "token", "refresh_token"),
        get_path(record, "tokens", "refresh_token"),
        get_path(record, "credentials", "refresh_token"),
    )


def session_token_from(record: dict[str, Any]) -> str | None:
    return first_non_empty(
        record.get("sessionToken"),
        record.get("session_token"),
        get_path(record, "token", "sessionToken"),
        get_path(record, "token", "session_token"),
        get_path(record, "credentials", "session_token"),
    )


def id_token_from(record: dict[str, Any]) -> str | None:
    return first_non_empty(
        record.get("idToken"),
        record.get("id_token"),
        get_path(record, "token", "idToken"),
        get_path(record, "token", "id_token"),
        get_path(record, "tokens", "id_token"),
        get_path(record, "credentials", "id_token"),
    )


def decode_base64_url(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def encode_base64_url_json(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def parse_jwt_payload(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    segments = token.split(".")
    if len(segments) < 2:
        return None
    try:
        payload = json.loads(decode_base64_url(segments[1]).decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def get_openai_auth_section(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    auth = payload.get("https://api.openai.com/auth")
    return auth if isinstance(auth, dict) else {}


def get_openai_profile_section(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    profile = payload.get("https://api.openai.com/profile")
    return profile if isinstance(profile, dict) else {}


def to_iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return to_iso_utc(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > 1e11 else value
        try:
            return to_iso_utc(datetime.fromtimestamp(seconds, tz=UTC))
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return to_iso_utc(parsed)


def timestamp_from_unix_seconds(value: Any) -> str | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return to_iso_utc(datetime.fromtimestamp(numeric, tz=UTC))
    except (OverflowError, OSError, ValueError):
        return None


def epoch_seconds_from_value(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value / 1000 if value > 1e11 else value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, str):
        normalized = normalize_timestamp(value)
        if normalized:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            return int(parsed.timestamp())
    return 0


def build_synthetic_codex_id_token(
    email: str | None,
    account_id: str | None,
    plan_type: str | None,
    user_id: str | None,
    expires_at: str | None,
    now: datetime | None = None,
) -> str | None:
    if not account_id:
        return None

    now = now or datetime.now(tz=UTC)
    now_seconds = int(now.timestamp())
    expires = epoch_seconds_from_value(expires_at) or now_seconds + 90 * 24 * 60 * 60
    auth_info: dict[str, Any] = {"chatgpt_account_id": account_id}

    if plan_type:
        auth_info["chatgpt_plan_type"] = plan_type
    if user_id:
        auth_info["chatgpt_user_id"] = user_id
        auth_info["user_id"] = user_id

    payload: dict[str, Any] = {
        "iat": now_seconds,
        "exp": expires,
        "https://api.openai.com/auth": auth_info,
    }
    if email:
        payload["email"] = email

    header = {"alg": "none", "typ": "JWT", "cpa_synthetic": True}
    return f"{encode_base64_url_json(header)}.{encode_base64_url_json(payload)}.synthetic"


def get_expires_in(expires_at: str | None, now: datetime | None = None) -> int | None:
    if not expires_at:
        return None
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or datetime.now(tz=UTC)
    return max(0, int((expires - now.astimezone(UTC)).total_seconds()))


def get_axonhub_last_refresh(expires_at: str | None, now: datetime | None = None) -> str:
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return to_iso_utc(expires - timedelta(hours=1))
        except ValueError:
            pass
    return to_iso_utc(now or datetime.now(tz=UTC))


def strip_unavailable(value: Any) -> Any:
    if isinstance(value, list):
        items = [strip_unavailable(item) for item in value]
        return [item for item in items if item is not None]
    if isinstance(value, dict):
        entries = {key: strip_unavailable(item) for key, item in value.items()}
        entries = {key: item for key, item in entries.items() if item is not None}
        return entries or None
    if value is None or value == "":
        return None
    return value


def to_email_key(email: str | None) -> str | None:
    if not email:
        return None
    return re.sub(r"(^_+|_+$)", "", re.sub(r"[^a-z0-9]+", "_", email.strip().lower()))


def has_identity(record: dict[str, Any]) -> bool:
    return bool(
        isinstance(record.get("user"), dict)
        or first_non_empty(
            record.get("email"),
            record.get("name"),
            get_path(record, "providerSpecificData", "chatgptAccountId"),
            get_path(record, "providerSpecificData", "chatgpt_account_id"),
            record.get("id"),
            get_path(record, "tokens", "id_token"),
        )
    )


def _parse_json_fragment(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def extract_json_values_from_text(text: str) -> list[Any]:
    values: list[Any] = []
    starts = {"{", "["}
    closers = {"{": "}", "[": "]"}

    for start_index, char in enumerate(text):
        if char not in starts:
            continue

        stack = [closers[char]]
        in_string = False
        escape = False
        for index in range(start_index + 1, len(text)):
            current = text[index]
            if in_string:
                if escape:
                    escape = False
                elif current == "\\":
                    escape = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current in starts:
                stack.append(closers[current])
            elif stack and current == stack[-1]:
                stack.pop()
                if not stack:
                    parsed = _parse_json_fragment(text[start_index : index + 1])
                    if parsed is not None:
                        values.append(parsed)
                    break
    return values


def parse_key_value_text(text: str, source_name: str) -> list[FoundSession]:
    aliases = {
        "accessToken": "accessToken",
        "access_token": "accessToken",
        "sessionToken": "sessionToken",
        "session_token": "sessionToken",
        "refreshToken": "refreshToken",
        "refresh_token": "refreshToken",
        "idToken": "idToken",
        "id_token": "idToken",
        "email": "email",
        "account_id": "account_id",
        "chatgpt_account_id": "account_id",
        "expires": "expires",
        "expires_at": "expires_at",
        "expired": "expired",
        "plan_type": "plan_type",
    }
    record: dict[str, Any] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(.+?)\s*$", line)
        if not match:
            continue
        raw_key, value = match.groups()
        key = aliases.get(raw_key.strip())
        if key and value.strip():
            record[key] = value.strip().strip('"').strip("'")

    if access_token_from(record):
        return [FoundSession(record, source_name=source_name, path="$text")]
    return []


def find_sessions(value: Any, source_name: str = "pasted-json") -> list[FoundSession]:
    found: list[FoundSession] = []
    visited: set[int] = set()

    def visit(item: Any, path: str) -> None:
        if isinstance(item, dict):
            marker = id(item)
            if marker in visited:
                return
            visited.add(marker)

            if access_token_from(item) and has_identity(item):
                found.append(FoundSession(item, source_name=source_name, path=path))
                return

            for key, child in item.items():
                if isinstance(child, str) and ("accessToken" in child or "access_token" in child):
                    for parsed in extract_json_values_from_text(child):
                        visit(parsed, f"{path}.{key}$json")
                else:
                    visit(child, f"{path}.{key}")
            return

        if isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, "$")
    return found


def parse_input_documents(text: str, source_name: str = "pasted-json") -> list[FoundSession]:
    if not isinstance(text, str) or not text.strip():
        return []

    parsed = _parse_json_fragment(text)
    if parsed is not None:
        found = find_sessions(parsed, source_name=source_name)
        if found:
            return found

    found: list[FoundSession] = []
    for index, value in enumerate(extract_json_values_from_text(text)):
        for item in find_sessions(value, source_name=source_name):
            suffix = "" if item.path == "$" else item.path[1:]
            found.append(FoundSession(item.value, source_name=item.source_name, path=f"$fragment[{index}]{suffix}"))

    if found:
        return found

    return parse_key_value_text(text, source_name=source_name)


def convert_session(
    record: dict[str, Any],
    *,
    source_name: str = "pasted-json",
    source_path: str | None = None,
    now: datetime | None = None,
) -> ConvertedSession:
    if not isinstance(record, dict):
        raise ValueError("session is not a JSON object")

    now = now or datetime.now(tz=UTC)
    access_token = access_token_from(record)
    if not access_token:
        raise ValueError("missing accessToken")

    session_token = session_token_from(record)
    refresh_token = refresh_token_from(record)
    input_id_token = id_token_from(record)

    payload = parse_jwt_payload(access_token)
    id_payload = parse_jwt_payload(input_id_token)
    auth = get_openai_auth_section(payload)
    id_auth = get_openai_auth_section(id_payload)
    profile = get_openai_profile_section(payload)

    expires_at = first_non_empty(
        timestamp_from_unix_seconds(payload.get("exp") if payload else None),
        normalize_timestamp(record.get("expires")),
        normalize_timestamp(record.get("expiresAt")),
        normalize_timestamp(record.get("expired")),
        normalize_timestamp(record.get("expires_at")),
    )
    email = first_non_empty(
        get_path(record, "user", "email"),
        record.get("email"),
        get_path(record, "credentials", "email"),
        get_path(record, "providerSpecificData", "email"),
        profile.get("email"),
        id_payload.get("email") if id_payload else None,
        payload.get("email") if payload else None,
    )
    account_id = first_non_empty(
        get_path(record, "account", "id"),
        record.get("account_id"),
        record.get("chatgptAccountId"),
        get_path(record, "providerSpecificData", "chatgptAccountId"),
        get_path(record, "providerSpecificData", "chatgpt_account_id"),
        get_path(record, "credentials", "chatgpt_account_id"),
        auth.get("chatgpt_account_id"),
        id_auth.get("chatgpt_account_id"),
        record.get("id") if record.get("provider") == "codex" else None,
    )
    user_id = first_non_empty(
        get_path(record, "user", "id"),
        record.get("user_id"),
        record.get("chatgptUserId"),
        get_path(record, "providerSpecificData", "chatgptUserId"),
        get_path(record, "providerSpecificData", "chatgpt_user_id"),
        auth.get("chatgpt_user_id"),
        auth.get("user_id"),
        id_auth.get("chatgpt_user_id"),
        id_auth.get("user_id"),
    )
    plan_type = first_non_empty(
        get_path(record, "account", "planType"),
        get_path(record, "account", "plan_type"),
        record.get("planType"),
        record.get("plan_type"),
        get_path(record, "providerSpecificData", "chatgptPlanType"),
        get_path(record, "providerSpecificData", "chatgpt_plan_type"),
        get_path(record, "credentials", "plan_type"),
        auth.get("chatgpt_plan_type"),
        id_auth.get("chatgpt_plan_type"),
    )
    exported_at = to_iso_utc(now)
    expires_in = get_expires_in(expires_at, now)
    source_type = "9router" if record.get("provider") == "codex" and record.get("authType") == "oauth" else "chatgpt_web_session"
    name = first_non_empty(email, source_name, "ChatGPT Account") or "ChatGPT Account"
    synthetic_id_token = None
    if not input_id_token:
        synthetic_id_token = build_synthetic_codex_id_token(email, account_id, plan_type, user_id, expires_at, now=now)
    id_token = first_non_empty(input_id_token, synthetic_id_token)

    cpa = {
        key: value
        for key, value in {
            "type": "codex",
            "account_id": account_id,
            "chatgpt_account_id": account_id,
            "email": email,
            "name": name,
            "plan_type": plan_type,
            "chatgpt_plan_type": plan_type,
            "id_token": id_token,
            "id_token_synthetic": True if synthetic_id_token else None,
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "session_token": session_token,
            "last_refresh": exported_at,
            "expired": expires_at,
            "disabled": True if record.get("disabled") else None,
        }.items()
        if value is not None
    }

    cockpit = {
        "type": "codex",
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token or "",
        "account_id": account_id,
        "last_refresh": exported_at,
        "email": email,
        "expired": expires_at,
        "account_note": first_non_empty(
            record.get("account_note"),
            record.get("accountInfo"),
            record.get("account_info"),
            record.get("note"),
            record.get("notes"),
            record.get("remark"),
        ),
    }

    sub2api_account = strip_unavailable(
        {
            "name": first_non_empty(name, email, source_name, "ChatGPT Account"),
            "platform": "openai",
            "type": "oauth",
            "concurrency": 10,
            "priority": 1,
            "credentials": {
                "access_token": access_token,
                "chatgpt_account_id": account_id,
                "chatgpt_user_id": user_id,
                "email": email,
                "expires_at": expires_at,
                "expires_in": expires_in,
                "plan_type": plan_type,
            },
            "extra": {
                "email": email,
                "email_key": to_email_key(email),
                "name": name,
                "auth_provider": first_non_empty(record.get("authProvider"), record.get("auth_provider")),
                "source": source_type,
                "last_refresh": exported_at,
            },
        }
    )
    priority = int(record.get("priority")) if str(record.get("priority", "")).isdigit() else 9
    is_active = record.get("isActive") if isinstance(record.get("isActive"), bool) else not bool(record.get("disabled"))
    created_at = normalize_timestamp(record.get("createdAt")) or exported_at
    updated_at = normalize_timestamp(record.get("updatedAt")) or exported_at
    nine_router = strip_unavailable(
        {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresAt": expires_at,
            "testStatus": first_non_empty(record.get("testStatus"), record.get("test_status"), "active"),
            "expiresIn": expires_in,
            "providerSpecificData": {
                "chatgptAccountId": account_id,
                "chatgptPlanType": plan_type,
            },
            "id": account_id,
            "provider": "codex",
            "authType": "oauth",
            "name": name,
            "email": email,
            "priority": priority,
            "isActive": is_active,
            "createdAt": created_at,
            "updatedAt": updated_at,
        }
    )
    axonhub = strip_unavailable(
        {
            "auth_mode": "chatgpt",
            "last_refresh": get_axonhub_last_refresh(expires_at, now),
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token or AXONHUB_PLACEHOLDER_REFRESH_TOKEN,
                "id_token": id_token,
            },
            "axonhub_refresh_token_placeholder": None if refresh_token else True,
            "axonhub_note": None if refresh_token else "refresh_token is a placeholder; access_token works only until it expires.",
        }
    )

    return ConvertedSession(
        source_name=source_name,
        source_path=source_path,
        email=email,
        name=name,
        expires_at=expires_at,
        cpa=cpa,
        cockpit={key: value for key, value in cockpit.items() if value is not None},
        sub2api_account=sub2api_account or {},
        nine_router=nine_router or {},
        axonhub=axonhub or {},
    )


def build_output_document(
    converted: list[ConvertedSession],
    output_format: str = "cockpit",
    *,
    now: datetime | None = None,
) -> Any:
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported output format: {output_format}")
    now = now or datetime.now(tz=UTC)
    if output_format == "sub2api":
        return {
            "exported_at": to_iso_utc(now),
            "proxies": [],
            "accounts": [item.sub2api_account for item in converted],
        }

    values = {
        "cockpit": [item.cockpit for item in converted],
        "cpa": [item.cpa for item in converted],
        "9router": [item.nine_router for item in converted],
        "axonhub": [item.axonhub for item in converted],
    }[output_format]
    return values[0] if len(values) == 1 else values


def convert_text(
    text: str,
    *,
    output_format: str = "cockpit",
    source_name: str = "pasted-json",
    now: datetime | None = None,
) -> ConversionResult:
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported output format: {output_format}")

    now = now or datetime.now(tz=UTC)
    sessions = parse_input_documents(text, source_name=source_name)
    converted: list[ConvertedSession] = []
    skipped: list[SkippedItem] = []

    for item in sessions:
        try:
            converted.append(
                convert_session(
                    item.value,
                    source_name=item.source_name,
                    source_path=item.path,
                    now=now,
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep per-source errors for caller.
            skipped.append(SkippedItem(item.source_name, item.path, str(exc)))

    if not sessions:
        skipped.append(SkippedItem(source_name, "$", "no session object containing accessToken was found"))

    return ConversionResult(
        sessions=sessions,
        converted=converted,
        skipped=skipped,
        output=build_output_document(converted, output_format, now=now),
    )


def convert_file(
    path: str | Path,
    *,
    output_format: str = "cockpit",
    now: datetime | None = None,
) -> ConversionResult:
    input_path = Path(path)
    text = input_path.read_text(encoding="utf-8-sig")
    return convert_text(text, output_format=output_format, source_name=input_path.name, now=now)
