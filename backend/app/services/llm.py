"""LLM adapters with explicit provider provenance and deterministic fallback."""
import json
import os
import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
LYZR_DEFAULT_URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"


def _json_env(name, default=None):
    try:
        value = json.loads(os.getenv(name, "{}"))
        return value if isinstance(value, dict) else (default or {})
    except (TypeError, ValueError):
        return default or {}


def _lyzr_agent_id(role):
    role_ids = _json_env("LYZR_AGENT_IDS")
    if role and role_ids.get(role):
        return str(role_ids[role]).strip()
    # A single configured agent is deliberately used only for the Chair.
    if role == "chair":
        return os.getenv("LYZR_AGENT_ID", "").strip()
    return ""


def _extract_lyzr_text(data):
    if not isinstance(data, dict):
        return None
    for key in ("response", "message", "output", "answer", "text"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_lyzr_text(nested)
    return None


def _call_lyzr(system, prompt, role, session_id=None):
    api_key = os.getenv("LYZR_API_KEY", "").strip()
    agent_id = _lyzr_agent_id(role)
    if not api_key or not agent_id:
        return None
    user_id = os.getenv("LYZR_USER_ID", "marketmind-demo").strip() or "marketmind-demo"
    session_prefix = os.getenv("LYZR_SESSION_ID", "marketmind").strip() or "marketmind"
    session_id = session_id or f"{session_prefix}-{role or 'agent'}"
    endpoint = os.getenv("LYZR_AGENT_ENDPOINT", LYZR_DEFAULT_URL).strip()
    message = f"SYSTEM INSTRUCTIONS:\n{system}\n\nTASK:\n{prompt}"
    try:
        response = requests.post(
            endpoint,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={
                "user_id": user_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "message": message,
                "system_prompt_variables": {},
                "filter_variables": {},
                "features": [],
            },
            timeout=45,
        )
        if response.status_code >= 400:
            return {"text": None, "provider": "Lyzr", "live": False,
                    "status_code": response.status_code, "error_code": "LYZR_HTTP_ERROR",
                    "error": f"Lyzr returned HTTP {response.status_code}: {response.text[:180]}"}
        text = _extract_lyzr_text(response.json())
        if not text:
            return {"text": None, "provider": "Lyzr", "live": False,
                    "status_code": response.status_code, "error_code": "LYZR_EMPTY_RESPONSE",
                    "error": "Lyzr returned no recognized response text"}
        return {"text": text, "provider": "Lyzr Inference v3", "live": True,
                "status_code": response.status_code, "error_code": None, "error": None,
                "agent_id": agent_id}
    except requests.Timeout:
        return {"text": None, "provider": "Lyzr", "live": False,
                "status_code": None, "error_code": "LYZR_TIMEOUT", "error": "Lyzr request timed out"}
    except requests.RequestException as exc:
        return {"text": None, "provider": "Lyzr", "live": False,
                "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                "error_code": "LYZR_REQUEST_ERROR", "error": str(exc)[:220]}
    except Exception as exc:
        return {"text": None, "provider": "Lyzr", "live": False,
                "status_code": None, "error_code": "LYZR_RESPONSE_ERROR", "error": str(exc)[:220]}


def _call_gemini(system, prompt):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return {"text": None, "provider": "deterministic fallback", "live": False,
                "status_code": None, "error_code": "GEMINI_KEY_MISSING", "error": "GEMINI_API_KEY is not configured"}
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    try:
        response = requests.post(
            GEMINI_URL,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"model": model, "input": prompt, "system_instruction": system, "store": False},
            timeout=45,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", response.text[:180])
            except Exception:
                detail = response.text[:180]
            code = "GEMINI_RATE_LIMITED" if response.status_code == 429 else "GEMINI_AUTH_ERROR" if response.status_code in (401, 403) else "GEMINI_HTTP_ERROR"
            return {"text": None, "provider": "Gemini", "live": False, "status_code": response.status_code,
                    "error_code": code, "error": str(detail)[:220]}
        data = response.json()
        answer = data.get("output_text")
        if not answer:
            for step in data.get("steps", []):
                if step.get("type") == "model_output":
                    answer = "\n".join(part.get("text", "") for part in step.get("content", []) if part.get("type") == "text").strip()
                    if answer:
                        break
        if answer:
            return {"text": answer, "provider": "Gemini Interactions API", "live": True,
                    "status_code": response.status_code, "error_code": None, "error": None}
        return {"text": None, "provider": "Gemini", "live": False, "status_code": response.status_code,
                "error_code": "GEMINI_EMPTY_RESPONSE", "error": "Gemini returned no text output"}
    except requests.Timeout:
        return {"text": None, "provider": "Gemini", "live": False, "status_code": None,
                "error_code": "GEMINI_TIMEOUT", "error": "Gemini request timed out"}
    except requests.RequestException as exc:
        return {"text": None, "provider": "Gemini", "live": False,
                "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                "error_code": "GEMINI_REQUEST_ERROR", "error": str(exc)[:220]}
    except Exception as exc:
        return {"text": None, "provider": "Gemini", "live": False, "status_code": None,
                "error_code": "GEMINI_RESPONSE_ERROR", "error": str(exc)[:220]}


def generate_result(system, prompt, use_lyzr=False, agent_role=None, session_id=None):
    """Try a role-mapped Lyzr agent first, then Gemini, otherwise return fallback metadata."""
    attempts = []
    if use_lyzr and _lyzr_agent_id(agent_role):
        lyzr = _call_lyzr(system, prompt, agent_role, session_id=session_id)
        if lyzr and lyzr.get("live"):
            lyzr["attempts"] = [{"provider": "Lyzr", "status": "success", "status_code": lyzr.get("status_code")}]
            return lyzr
        if lyzr:
            attempts.append({"provider": "Lyzr", "status": "failed", "status_code": lyzr.get("status_code"), "error_code": lyzr.get("error_code"), "error": lyzr.get("error")})
    if agent_role == "chair" and os.getenv("AGENT37_USE_FOR_CHAIR", "false").strip().lower() in ("1", "true", "yes"):
        try:
            from app.services.agent37 import run_agent as _run_agent37
            hosted = _run_agent37(f"SYSTEM INSTRUCTIONS:\n{system}\n\nTASK:\n{prompt}")
            if hosted.get("live"):
                hosted["attempts"] = attempts + [{"provider": "Agent 37 Cloud", "status": "success", "status_code": hosted.get("status_code")}]
                return hosted
            attempts.append({"provider": "Agent 37 Cloud", "status": "failed", "status_code": hosted.get("status_code"), "error": hosted.get("error")})
        except Exception as exc:
            attempts.append({"provider": "Agent 37 Cloud", "status": "failed", "error": str(exc)[:180]})
    gemini = _call_gemini(system, prompt)
    if gemini.get("live"):
        gemini["attempts"] = attempts + [{"provider": "Gemini", "status": "success", "status_code": gemini.get("status_code")}]
        return gemini
    attempts.append({"provider": "Gemini", "status": "failed", "status_code": gemini.get("status_code"), "error_code": gemini.get("error_code"), "error": gemini.get("error")})
    gemini["attempts"] = attempts
    return gemini


def provider_status():
    role_ids = _json_env("LYZR_AGENT_IDS")
    single_id = bool(os.getenv("LYZR_AGENT_ID", "").strip())
    return {
        "gemini": {"configured": bool(os.getenv("GEMINI_API_KEY", "").strip()), "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash")},
        "lyzr": {"api_key_configured": bool(os.getenv("LYZR_API_KEY", "").strip()),
                 "configured": bool(os.getenv("LYZR_API_KEY", "").strip() and (role_ids or single_id)),
                 "single_chair_agent_configured": single_id,
                 "role_agents_configured": sorted(role_ids.keys()),
                 "endpoint": os.getenv("LYZR_AGENT_ENDPOINT", LYZR_DEFAULT_URL)},
    }
