import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List

import httpx

from backend.curriculum_kb import CurriculumKB

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
    },
    "google_ai_studio": {
        "label": "Google AI Studio",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
    },
    "other": {
        "label": "Other Providers",
        "base_url": "",
    },
}

LESSON_KEYWORDS = {
    "lesson", "teach", "teacher", "student", "grade", "curriculum", "standard",
    "math", "science", "english", "history", "biology", "physics", "chemistry",
    "quiz", "exam", "homework", "syllabus", "courseware", "activity", "rubric",
    "pedagogy", "classroom", "learning", "study", "explain", "worksheet", "textbook",
    "教案", "备课", "课程", "教学", "学生", "年级", "课标", "作业", "课堂",
    "備課", "課程", "教學", "學生", "年級", "課綱", "作業", "課堂",
    "lección", "leçon", "unterricht", "授業", "수업", "урок", "pelajaran",
}

UNRELATED_HINT_KEYWORDS = {
    "stock price", "crypto", "bitcoin", "betting", "gambling", "horoscope",
    "celebrity gossip", "lottery", "buy shoes", "flight ticket",
}


def classify_intent(prompt: str) -> str:
    low = (prompt or "").lower()
    if any(k in low for k in UNRELATED_HINT_KEYWORDS):
        return "unrelated"
    if any(k in low for k in LESSON_KEYWORDS):
        return "lesson_prep"
    if len(low.split()) >= 3 and not any(w in low for w in ["weather today", "joke about politics"]):
        return "lesson_prep"
    return "unrelated"


def infer_thinking_levels(provider: str, model_id: str, meta: Dict[str, Any] = None) -> List[str]:
    m = (model_id or "").lower()
    meta = meta or {}
    if provider == "google_ai_studio":
        if meta.get("thinking") or any(k in m for k in ("2.5", "3.", "thinking")):
            return ["default", "off", "low", "medium", "high"]
        return ["default"]
    if provider in ("openai", "other"):
        if any(k in m for k in ("o1", "o3", "o4", "gpt-5", "reasoner", "r1", "thinking")):
            return ["default", "low", "medium", "high"]
        return ["default", "low", "medium", "high"]
    if provider == "deepseek":
        if "reasoner" in m or "r1" in m:
            return ["default", "low", "medium", "high"]
        return ["default"]
    return ["default"]


async def validate_and_fetch_models(
    provider: str,
    api_key: str,
    base_url: str = "",
    model: str = "",
    thinking_level: str = "default",
) -> Dict[str, Any]:
    if provider not in PROVIDERS:
        return {"valid": False, "models": [], "thinking_levels": {}, "error": f"Unsupported provider: {provider}"}

    cfg = PROVIDERS[provider]
    endpoint = (base_url or cfg["base_url"]).rstrip("/")
    key = (api_key or "").strip()

    if not endpoint or not key:
        return {
            "valid": False,
            "models": [],
            "thinking_levels": {},
            "thinking_validated": False,
            "error": "Both Base URL and API Key are required.",
        }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            if provider == "google_ai_studio":
                resp = await client.get(f"{endpoint}/models", params={"key": key})
                resp.raise_for_status()
                data = resp.json()
                models: List[str] = []
                thinking_map: Dict[str, List[str]] = {}
                for item in data.get("models", []):
                    if "generateContent" in item.get("supportedGenerationMethods", []):
                        mid = item["name"].replace("models/", "")
                        models.append(mid)
                        thinking_map[mid] = infer_thinking_levels(provider, mid, item)
            else:
                resp = await client.get(
                    f"{endpoint}/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", []) if m.get("id")]
                thinking_map = {mid: infer_thinking_levels(provider, mid) for mid in models}

            target_model = model if model in models else (models[0] if models else "")
            thinking_validated = True
            thinking_note = "Model default"

            if target_model and thinking_level and thinking_level != "default":
                if provider == "google_ai_studio":
                    budget_map = {"off": 0, "low": 1024, "medium": 2048, "high": 4096}
                    probe_body = {
                        "contents": [{"role": "user", "parts": [{"text": "ok"}]}],
                        "generationConfig": {
                            "maxOutputTokens": 1,
                            "thinkingConfig": {"thinkingBudget": budget_map.get(thinking_level, 1024)},
                        },
                    }
                    p_resp = await client.post(
                        f"{endpoint}/models/{target_model}:generateContent",
                        params={"key": key},
                        json=probe_body,
                    )
                    if p_resp.status_code >= 400:
                        thinking_validated = False
                        thinking_note = f"Thinking level '{thinking_level}' rejected ({p_resp.status_code})"
                    else:
                        thinking_note = f"Thinking level '{thinking_level}' verified"
                else:
                    probe_body = {
                        "model": target_model,
                        "messages": [{"role": "user", "content": "ok"}],
                        "max_tokens": 1,
                        "reasoning_effort": thinking_level,
                    }
                    p_resp = await client.post(
                        f"{endpoint}/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json=probe_body,
                    )
                    if p_resp.status_code >= 400:
                        thinking_validated = False
                        thinking_note = f"Thinking level '{thinking_level}' rejected ({p_resp.status_code})"
                    else:
                        thinking_note = f"Thinking level '{thinking_level}' verified"

            return {
                "valid": True,
                "models": models,
                "thinking_levels": thinking_map,
                "thinking_validated": thinking_validated,
                "thinking_note": thinking_note,
                "source": "live",
            }
    except Exception as exc:
        return {"valid": False, "models": [], "thinking_levels": {}, "thinking_validated": False, "error": str(exc)}


def _build_system_prompt(memory: Dict[str, Any], standards_context: str, language: str, thinking_level: str) -> str:
    parts = [
        "You are aiforteachers, an intelligent courseware and lesson-preparation assistant.",
        "Follow this workflow: analyze subject and grade level, align with curriculum standards, and generate a clear, classroom-ready lesson plan or teaching response.",
        f"Respond in the user's language (UI language preference: {language}).",
    ]
    if memory.get("focus_areas"):
        parts.append(f"Teacher focus areas: {memory['focus_areas']}")
    if memory.get("chat_style"):
        parts.append(f"Preferred teaching/chat style: {memory['chat_style']}")
    if standards_context:
        parts.append(standards_context)
    if thinking_level and thinking_level != "default":
        parts.append(f"Reasoning depth preference: {thinking_level}.")
    return "\n\n".join(parts)


async def stream_lesson_response(
    prompt: str,
    history: List[Dict[str, Any]],
    settings: Dict[str, Any],
    memory: Dict[str, Any],
    kb: CurriculumKB,
    use_web_search: bool = False,
) -> AsyncGenerator[str, None]:
    intent = classify_intent(prompt)
    if intent == "unrelated":
        for step in [
            "Checking user intent against educational & lesson-preparation scope...\n",
            "Prompt appears unrelated to teaching or learning.\n",
        ]:
            yield f"data: {json.dumps({'type': 'thinking', 'delta': step})}\n\n"
            await asyncio.sleep(0.08)
        msg = "Sorry, this function is not available for now. I'm currently focused on helping teachers with lesson preparation, curriculum alignment, and classroom materials—feel free to ask about any subject or grade level!"
        yield f"data: {json.dumps({'type': 'content', 'delta': msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    matches = kb.search(query=prompt, limit=4)
    standards_ctx = kb.format_context(matches)
    provider = settings.get("provider", "openai")
    if provider not in PROVIDERS:
        provider = "other"
    cfg = PROVIDERS[provider]
    endpoint = (settings.get("base_url") or cfg["base_url"]).rstrip("/")
    api_key = (settings.get("api_key") or "").strip()
    model = (settings.get("model") or "").strip()
    thinking_level = settings.get("thinking_level", "default")

    if not api_key or not endpoint or not model:
        yield f"data: {json.dumps({'type': 'error', 'message': 'API is not configured. Open Settings > API, enter your Base URL and API Key, and click Validate & Fetch Models.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    sys_prompt = _build_system_prompt(memory, standards_ctx, settings.get("language", "en"), thinking_level)
    think_msg = f"Consulting {cfg['label']} ({model}) with {len(matches)} curriculum standard(s)...\n"
    yield f"data: {json.dumps({'type': 'thinking', 'delta': think_msg})}\n\n"

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for h in history[-8:]:
        messages_payload.append({"role": h["role"], "content": h["content"]})
    messages_payload.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            if provider == "google_ai_studio":
                contents = [
                    {
                        "role": "user" if m["role"] == "user" else "model",
                        "parts": [{"text": m["content"]}],
                    }
                    for m in messages_payload if m["role"] != "system"
                ]
                body: Dict[str, Any] = {
                    "systemInstruction": {"parts": [{"text": sys_prompt}]},
                    "contents": contents,
                }
                if thinking_level and thinking_level != "default":
                    budget_map = {"off": 0, "low": 1024, "medium": 2048, "high": 4096}
                    body["generationConfig"] = {"thinkingConfig": {"thinkingBudget": budget_map.get(thinking_level, 1024)}}
                async with client.stream(
                    "POST",
                    f"{endpoint}/models/{model}:streamGenerateContent",
                    params={"alt": "sse", "key": api_key},
                    json=body,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        evt = json.loads(line[6:].strip())
                        for cand in evt.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                if part.get("thought"):
                                    yield f"data: {json.dumps({'type': 'thinking', 'delta': part.get('text', '')})}\n\n"
                                elif part.get("text"):
                                    yield f"data: {json.dumps({'type': 'content', 'delta': part.get('text', '')})}\n\n"
            else:
                body = {
                    "model": model,
                    "messages": messages_payload,
                    "stream": True,
                }
                if thinking_level in ("low", "medium", "high"):
                    body["reasoning_effort"] = thinking_level
                async with client.stream(
                    "POST",
                    f"{endpoint}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        evt = json.loads(raw)
                        for choice in evt.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("reasoning_content"):
                                yield f"data: {json.dumps({'type': 'thinking', 'delta': delta['reasoning_content']})}\n\n"
                            if delta.get("content"):
                                yield f"data: {json.dumps({'type': 'content', 'delta': delta['content']})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
