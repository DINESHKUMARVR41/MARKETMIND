"""Agent 37 Cloud adapter: explicit instance provisioning and Responses API calls."""
import os
import requests

BASE = "https://api.agent37.com/v1"


def _key():
    return os.getenv("AGENT37_API_KEY", "").strip()


def status():
    return {
        "api_key_configured": bool(_key()),
        "instance_configured": bool(os.getenv("AGENT37_INSTANCE_URL", "").strip()),
        "inference_configured": bool(os.getenv("AGENT37_INSTANCE_URL", "").strip() and os.getenv("AGENT37_INSTANCE_API_KEY", "").strip()),
        "instance_id_present": bool(os.getenv("AGENT37_INSTANCE_ID", "").strip()),
        "template": os.getenv("AGENT37_TEMPLATE", "agent37-hermes"),
        "mode": "Agent 37 Cloud API" if _key() else "not configured",
        "note": "Provisioning can incur metered compute/storage charges; no instance is created automatically."
    }


def provision_instance(template=None):
    key = _key()
    if not key:
        return {"ok": False, "error": "AGENT37_API_KEY is not configured"}
    selected_template = template or os.getenv("AGENT37_TEMPLATE", "agent37-hermes")
    try:
        response = requests.post(
            f"{BASE}/instances",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"template": selected_template}, timeout=90,
        )
        if response.status_code >= 400:
            return {"ok": False, "state": "authentication_rejected" if response.status_code in (401, 403) else "provisioning_failed",
                    "operation_succeeded": False, "status_code": response.status_code,
                    "error": f"Agent 37 provisioning request failed: HTTP {response.status_code}"}
        data = response.json()
        instance_id = data.get("id") or data.get("instance_id")
        ports = data.get("ports") or []
        default_port = next((item for item in ports if item.get("default")), ports[0] if ports else {})
        instance_url = default_port.get("url") or data.get("url")
        return {"ok": True, "state": "operation_succeeded", "operation_succeeded": True,
                "status_code": response.status_code,
                "instance_id": instance_id, "instance_url": instance_url,
                "next_steps": ["Copy instance_id to AGENT37_INSTANCE_ID", "Copy instance_url to AGENT37_INSTANCE_URL", "Configure the Hermes API_SERVER_KEY inside the instance and copy it to AGENT37_INSTANCE_API_KEY", "Restart MARKETMIND backend and call /api/integrations/agent37/test"]}
    except requests.Timeout:
        return {"ok": False, "state": "network_failure", "operation_succeeded": False,
                "error": "Agent 37 provisioning request timed out"}
    except requests.RequestException:
        return {"ok": False, "state": "network_failure", "operation_succeeded": False,
                "error": "Agent 37 provisioning request could not reach the service"}
    except Exception as exc:
        return {"ok": False, "state": "response_error", "operation_succeeded": False,
                "error": f"Agent 37 returned an unreadable response ({type(exc).__name__})"}


def run_agent(prompt, previous_response_id=None, model=None):
    instance_url = os.getenv("AGENT37_INSTANCE_URL", "").strip().rstrip("/")
    if not instance_url or not os.getenv("AGENT37_INSTANCE_API_KEY", "").strip():
        return {"text": None, "provider": "Agent 37", "live": False,
                "state": "credentials_missing", "operation_succeeded": False,
                "error": "Set AGENT37_API_KEY, AGENT37_INSTANCE_URL and AGENT37_INSTANCE_API_KEY (the instance gateway key) after provisioning/configuring an instance."}
    payload = {"model": model or os.getenv("AGENT37_MODEL", "hermes"), "input": prompt, "stream": False}
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    try:
        response = requests.post(
            f"{instance_url}/v1/responses",
            headers={"Authorization": f"Bearer {os.getenv('AGENT37_INSTANCE_API_KEY', '').strip()}", "Content-Type": "application/json"},
            json=payload, timeout=120,
        )
        if response.status_code >= 400:
            rejected = response.status_code in (401, 403)
            return {"text": None, "provider": "Agent 37", "live": False,
                    "state": "authentication_rejected" if rejected else "operation_failed",
                    "operation_succeeded": False, "status_code": response.status_code,
                    "error": f"Agent 37 hosted inference failed: HTTP {response.status_code}"}
        data = response.json()
        text = data.get("output_text")
        if not text:
            chunks = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in ("output_text", "text") and content.get("text"):
                        chunks.append(content["text"])
            text = "\n".join(chunks).strip()
        return {"text": text or None, "provider": "Agent 37 Cloud", "live": bool(text),
                "state": "operation_succeeded" if text else "empty_response",
                "operation_succeeded": bool(text),
                "status_code": response.status_code, "response_id": data.get("id"),
                "error": None if text else "Agent 37 returned no text output"}
    except requests.Timeout:
        return {"text": None, "provider": "Agent 37", "live": False, "state": "network_failure",
                "operation_succeeded": False, "error": "Agent 37 hosted inference timed out"}
    except requests.RequestException:
        return {"text": None, "provider": "Agent 37", "live": False, "state": "network_failure",
                "operation_succeeded": False, "error": "Agent 37 hosted inference could not reach the service"}
    except Exception as exc:
        return {"text": None, "provider": "Agent 37", "live": False, "state": "response_error",
                "operation_succeeded": False, "error": f"Agent 37 returned an unreadable response ({type(exc).__name__})"}
