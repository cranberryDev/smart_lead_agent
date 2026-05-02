from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from api.schemas import (
    Contact,
    FollowUpAgentResponse,
    FollowUpEmail,
    FollowUpEnrichment,
    LeadPayload,
)


def _contact_display_name(contact: Contact) -> str:
    if contact.full_name and contact.full_name.strip():
        return contact.full_name.strip()
    parts = [contact.first_name or "", contact.last_name or ""]
    joined = " ".join(p.strip() for p in parts if p and p.strip())
    return joined or "Unknown"


def _lead_user_payload_json(lead: LeadPayload) -> str:
    """Only structured lead data — instructions live in AI Foundry agent config."""
    payload = lead.model_dump(mode="json")
    payload["contact"]["_display_name"] = _contact_display_name(lead.contact)
    return json.dumps(payload, indent=2, default=str)


def _resolve_chat_url() -> str | None:
    direct = (os.getenv("AI_FOUNDRY_CHAT_URL") or "").strip()
    if direct:
        return direct
    base = (os.getenv("AI_FOUNDRY_ENDPOINT") or "").rstrip("/")
    deployment = (os.getenv("AI_FOUNDRY_DEPLOYMENT") or "").strip()
    api_ver = (os.getenv("AI_FOUNDRY_API_VERSION") or "2024-08-01-preview").strip()
    if base and deployment:
        return (
            f"{base}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={api_ver}"
        )
    return None


def _auth_headers(api_key: str) -> dict[str, str]:
    if os.getenv("AI_FOUNDRY_USE_BEARER", "").lower() in ("1", "true", "yes"):
        return {"Authorization": f"Bearer {api_key}"}
    header_name = os.getenv("AI_FOUNDRY_API_KEY_HEADER", "api-key")
    return {header_name: api_key}


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _extract_markdown_json_blocks(text: str) -> list[str]:
    inner: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE):
        block = m.group(1).strip()
        if block:
            inner.append(block)
    return inner


def _first_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None


def _json_parse_candidates(text: str) -> list[str]:
    text = text.strip()
    out: list[str] = []
    if not text:
        return out
    out.extend(_extract_markdown_json_blocks(text))
    whole_fenced = _strip_json_fence(text)
    if whole_fenced != text:
        out.append(whole_fenced)
    out.append(text)
    balanced = _first_balanced_json_object(text)
    if balanced:
        out.append(balanced)

    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _allow_plaintext() -> bool:
    raw = (os.getenv("AI_FOUNDRY_ALLOW_PLAINTEXT") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _looks_like_internal_lead_summary(text: str) -> bool:
    t = text.lower()
    markers = (
        "lead overview",
        "internal use",
        "contact details",
        "**lead id",
        "lead id:",
        "company",
        "website form",
        "source:",
    )
    hits = sum(1 for m in markers if m in t)
    return hits >= 3 or ("lead overview" in t and "contact" in t)


def _normalize_legacy_flat_response(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("email"), dict):
        return data
    body = None
    for k in ("draft_follow_up", "draft_followup", "message", "body", "text", "content"):
        v = data.get(k)
        if v not in (None, ""):
            body = v
            break
    if body is None:
        return data
    drop = {"draft_follow_up", "draft_followup", "message", "body", "text", "content"}
    out = {k: v for k, v in data.items() if k not in drop}
    out["email"] = {
        "subject": str(data.get("subject") or ""),
        "body": str(body),
    }
    if not isinstance(out.get("enrichment"), dict):
        out["enrichment"] = {}
    return out


def _ensure_email_dict(data: dict[str, Any]) -> dict[str, Any]:
    em = data.get("email")
    if isinstance(em, str):
        data["email"] = {"subject": "", "body": em}
    elif not isinstance(em, dict):
        data["email"] = {"subject": "", "body": ""}
    else:
        data["email"] = {
            "subject": str(em.get("subject") or ""),
            "body": str(em.get("body") or ""),
        }
    return data


def _ensure_enrichment_dict(data: dict[str, Any]) -> dict[str, Any]:
    en = data.get("enrichment")
    if not isinstance(en, dict):
        data["enrichment"] = {}
    return data


def _normalize_llm_dict_to_agent_shape(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    data = _normalize_legacy_flat_response(data)
    data = _ensure_email_dict(data)
    data = _ensure_enrichment_dict(data)
    cs = data.get("confidence_score")
    if cs is None:
        data["confidence_score"] = 0.0
    else:
        try:
            data["confidence_score"] = float(cs)
        except (TypeError, ValueError):
            data["confidence_score"] = 0.0
    if not str(data.get("status") or "").strip():
        data["status"] = "success"
    return data


def _plaintext_to_agent_response(text: str, lead_id: str) -> FollowUpAgentResponse:
    cleaned = text.strip()
    if _looks_like_internal_lead_summary(cleaned):
        return FollowUpAgentResponse(
            status="success",
            lead_id=lead_id,
            email=FollowUpEmail(subject="Lead summary (model returned prose)", body=cleaned),
            enrichment=FollowUpEnrichment(),
            confidence_score=0.25,
        )
    return FollowUpAgentResponse(
        status="success",
        lead_id=lead_id,
        email=FollowUpEmail(subject="", body=cleaned),
        enrichment=FollowUpEnrichment(),
        confidence_score=0.5,
    )


def _parse_agent_output_from_text(text: str, lead_id: str) -> FollowUpAgentResponse:
    if not text.strip():
        raise ValueError(
            "Model returned empty content. Check Foundry deployment and max_tokens."
        )
    last_err: Exception | None = None
    for raw in _json_parse_candidates(text):
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                continue
            data = _normalize_llm_dict_to_agent_shape(data)
            if not str(data.get("lead_id") or "").strip():
                data["lead_id"] = lead_id
            return FollowUpAgentResponse.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e

    preview = text.strip()
    if len(preview) > 400:
        preview = preview[:400] + "…"
    if _allow_plaintext():
        return _plaintext_to_agent_response(text, lead_id)

    hint = f" Last error: {last_err}." if last_err else ""
    raise ValueError(
        "Could not parse model output as agent JSON (status, lead_id, email, enrichment, confidence_score)."
        f"{hint}"
        " Or set AI_FOUNDRY_ALLOW_PLAINTEXT=true (default is true) to accept prose."
        f" Raw preview: {preview!r}"
    )


def _extract_chat_completion_content(data: dict[str, Any]) -> str:
    err = data.get("error")
    if err:
        if isinstance(err, dict):
            raise ValueError(err.get("message") or json.dumps(err))
        raise ValueError(str(err))

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(
            "Foundry response missing choices — "
            f"top-level keys: {list(data.keys())}"
        )

    ch0 = choices[0]
    if not isinstance(ch0, dict):
        raise ValueError("Foundry choices[0] is not an object")

    if ch0.get("text") is not None:
        return str(ch0["text"])

    msg = ch0.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if content is not None:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts.append(str(part.get("text", "")))
                        elif "text" in part:
                            parts.append(str(part["text"]))
                    elif isinstance(part, str):
                        parts.append(part)
                joined = "".join(parts).strip()
                if joined:
                    return joined
            return str(content)

        refusal = msg.get("refusal")
        if refusal:
            raise ValueError(f"Model refused to answer: {refusal}")

        raise ValueError(f"Foundry message missing content: {msg!r}")

    raise ValueError(f"Unexpected choice shape: {ch0!r}")


async def generate_followup(lead: LeadPayload) -> FollowUpAgentResponse:
    """
    Call your Microsoft Foundry / Azure OpenAI-compatible chat deployment.
    Prompts and persona are configured on Foundry — this sends user role + lead JSON only.

    Env:
      - AI_FOUNDRY_API_KEY (required)
      - Either AI_FOUNDRY_CHAT_URL (full POST URL), or AI_FOUNDRY_ENDPOINT + AI_FOUNDRY_DEPLOYMENT
      - Optional: AI_FOUNDRY_API_VERSION, AI_FOUNDRY_USE_BEARER, AI_FOUNDRY_API_KEY_HEADER,
        AI_FOUNDRY_MODEL, AI_FOUNDRY_TEMPERATURE, AI_FOUNDRY_MAX_TOKENS,
        AI_FOUNDRY_ALLOW_PLAINTEXT — default true; set false to require strict JSON only
    """
    url = _resolve_chat_url()
    api_key = os.getenv("AI_FOUNDRY_API_KEY")
    if not api_key or not url:
        raise RuntimeError(
            "Set AI_FOUNDRY_API_KEY and a chat URL: AI_FOUNDRY_CHAT_URL "
            "or AI_FOUNDRY_ENDPOINT + AI_FOUNDRY_DEPLOYMENT"
        )

    body: dict[str, Any] = {
        "messages": [
            {"role": "user", "content": _lead_user_payload_json(lead)},
        ],
    }
    if model := os.getenv("AI_FOUNDRY_MODEL"):
        body["model"] = model.strip()
    if temp := os.getenv("AI_FOUNDRY_TEMPERATURE"):
        body["temperature"] = float(temp)
    if mt := os.getenv("AI_FOUNDRY_MAX_TOKENS"):
        body["max_tokens"] = int(mt)

    headers = {"Content-Type": "application/json", **_auth_headers(api_key)}
    timeout = httpx.Timeout(120.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=body, headers=headers)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = resp.text[:2000] if resp.text else str(e)
            raise RuntimeError(f"Foundry HTTP {resp.status_code}: {detail}") from e
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Foundry returned non-JSON body (first 500 chars): {resp.text[:500]!r}"
            ) from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from Foundry, got {type(data).__name__}")

    text = _extract_chat_completion_content(data)
    parsed = _parse_agent_output_from_text(text, lead.lead_id)
    return parsed.model_copy(update={"lead_id": lead.lead_id})
