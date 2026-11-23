"""BAND Agent API bridge with identity validation and honest delivery metadata."""
import os
import json
import socket
import ssl
import time
from urllib.parse import urlparse
import requests

BASE = "https://app.band.ai/api/v1/agent"
ROLES = ["analyst", "news", "bull", "bear", "risk", "chair"]


def _elapsed_ms(started):
    return round((time.perf_counter() - started) * 1000, 1)


def _network_exception(exc):
    """Return safe exception diagnostics without serializing exception text or request data."""
    if isinstance(exc, requests.exceptions.ProxyError):
        description, kind = "Proxy connection or negotiation failed.", "proxy_error"
    elif isinstance(exc, requests.exceptions.SSLError):
        description, kind = "TLS handshake or certificate validation failed.", "tls_error"
    elif isinstance(exc, requests.exceptions.ConnectTimeout):
        description, kind = "Connection establishment timed out.", "connect_timeout"
    elif isinstance(exc, requests.exceptions.ReadTimeout):
        description, kind = "The server response timed out.", "read_timeout"
    elif isinstance(exc, requests.exceptions.Timeout):
        description, kind = "The HTTP request timed out.", "timeout"
    elif isinstance(exc, requests.exceptions.ConnectionError):
        description, kind = "The HTTP client could not establish or maintain a connection.", "connection_error"
    elif isinstance(exc, requests.exceptions.RequestException):
        description, kind = "The HTTP client request failed before a usable response was received.", "request_error"
    elif isinstance(exc, ssl.SSLError):
        description, kind = "TLS handshake or certificate validation failed.", "tls_error"
    elif isinstance(exc, socket.gaierror):
        description, kind = "Hostname resolution failed.", "dns_error"
    elif isinstance(exc, (TimeoutError, socket.timeout)):
        description, kind = "The network operation timed out.", "timeout"
    elif isinstance(exc, PermissionError):
        description, kind = "Outbound socket access was denied by operating-system permissions.", "socket_permission_denied"
    elif isinstance(exc, OSError):
        description, kind = "The network operation failed at the operating-system socket layer.", "socket_error"
    else:
        description, kind = "The network diagnostic failed unexpectedly.", "diagnostic_error"
    response = getattr(exc, "response", None)
    result = {"exception_class": type(exc).__name__, "error_description": description,
              "network_error_kind": kind,
              "http_status": getattr(response, "status_code", None),
              "underlying_exception_classes": _exception_chain(exc)}
    if isinstance(exc, socket.gaierror):
        result["resolver_error_code"] = exc.errno
    return result


def _exception_chain(exc):
    """Expose exception type names only; never stringify exception arguments."""
    found, queue, seen = [], [exc], set()
    while queue and len(found) < 8:
        current = queue.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        found.append(type(current).__name__)
        nested = [getattr(current, "__cause__", None), getattr(current, "__context__", None),
                  getattr(current, "reason", None), getattr(current, "original_error", None)]
        queue.extend(item for item in nested if isinstance(item, BaseException))
        queue.extend(arg for arg in getattr(current, "args", ()) if isinstance(arg, BaseException))
    return found


def connectivity_diagnostic():
    """Credential-free connectivity probe; performs DNS/TLS and one unauthenticated GET only."""
    parsed = urlparse(BASE)
    host, port = parsed.hostname, parsed.port or 443
    report = {"base_url": BASE, "identity_path": "/me", "credentials_sent": False,
              "messages_sent": False, "proxy": {"requests_trust_env": True,
              "environment_proxy_names": [name for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy") if os.getenv(name)],
              "no_proxy_configured": bool(os.getenv("NO_PROXY") or os.getenv("no_proxy"))},
              "timeout_configuration_seconds": {"direct_tcp_connect": 5,
                                                 "direct_tls_handshake": 5,
                                                 "http_probe_connect": 5,
                                                 "http_probe_response": 8,
                                                 "authenticated_identity_request": 12}}

    started = time.perf_counter()
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        report["dns"] = {"status": "resolved", "address_count": len(addresses), "elapsed_ms": _elapsed_ms(started)}
    except Exception as exc:
        report["dns"] = {"status": "failed", "elapsed_ms": _elapsed_ms(started), **_network_exception(exc)}
        addresses = []

    raw = None
    tcp_started = time.perf_counter()
    if not addresses:
        report["direct_tcp"] = {"status": "not_attempted_dns_failed", "elapsed_ms": 0}
        report["direct_tls"] = {"status": "not_attempted_tcp_unavailable", "elapsed_ms": 0}
    else:
        tcp_connected = False
        try:
            # Direct route only; the HTTP probe below uses Requests' configured proxy.
            family, socktype, proto, _canonname, sockaddr = addresses[0]
            raw = socket.socket(family, socktype, proto)
            raw.settimeout(5)
            raw.connect(sockaddr)
            tcp_connected = True
            report["direct_tcp"] = {"status": "succeeded", "elapsed_ms": _elapsed_ms(tcp_started)}
        except Exception as exc:
            report["direct_tcp"] = {"status": "failed", "elapsed_ms": _elapsed_ms(tcp_started), **_network_exception(exc)}
            report["direct_tls"] = {"status": "not_attempted_tcp_unavailable", "elapsed_ms": 0}

        if tcp_connected and raw is not None:
            tls_started = time.perf_counter()
            try:
                with ssl.create_default_context().wrap_socket(raw, server_hostname=host):
                    raw = None  # TLS wrapper closed the underlying socket.
                report["direct_tls"] = {"status": "succeeded", "elapsed_ms": _elapsed_ms(tls_started)}
            except Exception as exc:
                report["direct_tls"] = {"status": "failed", "elapsed_ms": _elapsed_ms(tls_started), **_network_exception(exc)}
            finally:
                if raw is not None:
                    raw.close()
        elif raw is not None:
            raw.close()

    started = time.perf_counter()
    try:
        # No API key, authorization header, body, or BAND message is sent.
        response = requests.get(f"{BASE}/me", timeout=(5, 8))
        probe_status = "proxy_auth_required" if response.status_code == 407 else "response_received"
        report["http_probe"] = {"status": probe_status, "http_status": response.status_code,
                                "elapsed_ms": _elapsed_ms(started),
                                "note": "Unauthenticated probe only; HTTP 401/403 is an expected reachable response."}
    except Exception as exc:
        report["http_probe"] = {"status": "failed", "elapsed_ms": _elapsed_ms(started), **_network_exception(exc)}
    report["proxy"]["selected_proxy_types"] = sorted(requests.utils.get_environ_proxies(f"https://{host}/").keys())
    return report


def _config():
    try:
        keys = json.loads(os.getenv("BAND_AGENT_KEYS", "{}"))
        if not isinstance(keys, dict): keys = {}
    except Exception:
        keys = {}
    try:
        peers = json.loads(os.getenv("BAND_AGENT_PEERS", "{}"))
        if not isinstance(peers, dict): peers = {}
    except Exception:
        peers = {}
    peers = {role: peer for role, peer in peers.items() if isinstance(peer, dict)}
    shared_key = os.getenv("BAND_AGENT_API_KEY", "").strip()
    if shared_key:
        # A shared key means one orchestrator identity sends the room messages.
        # Distinct role identities require distinct per-role Agent API keys.
        for role in ROLES:
            keys.setdefault(role, shared_key)
    return keys, peers, os.getenv("BAND_CHAT_ID", "").strip()


def status():
    keys, peers, room = _config()
    single = bool(os.getenv("BAND_AGENT_API_KEY", "").strip())
    missing_keys = [role for role in ROLES if not keys.get(role)]
    missing_peers = [role for role in ROLES if not peers.get(role, {}).get("id") or not peers.get(role, {}).get("handle")]
    ready = bool(room and (single or (not missing_keys and not missing_peers)))
    return {"configured": ready, "chat_id_present": bool(room), "agent_count": 1 if single else len([r for r in ROLES if keys.get(r)]),
            "agents_with_keys": 1 if single else len([r for r in ROLES if keys.get(r)]),
            "sender_identity": "MARKETMIND" if single else None,
            "sender_roles_available": [] if single else [r for r in ROLES if keys.get(r)],
            "peer_handles": len([r for r in ROLES if peers.get(r, {}).get("id") and peers.get(r, {}).get("handle")]),
            "missing_agent_keys": [] if single else missing_keys,
            "missing_peer_mappings": [] if single else missing_peers,
            "identity_mode": "single BAND agent" if single else "per-role identities",
            "mode": "MARKETMIND room messages" if ready and single else ("live mention-routed messages" if ready else "BAND setup incomplete")}


def validate_identity(role="analyst"):
    keys, peers, room = _config()
    key = keys.get(role)
    if not key:
        return {"ok": False, "state": "credentials_missing", "identity_authenticated": False,
                "operation_succeeded": False, "room_access": None,
                "error": "No BAND API key is configured for this role."}
    headers = {"X-API-Key": key}
    identity_started = time.perf_counter()
    try:
        me = requests.get(f"{BASE}/me", headers=headers, timeout=12)
        identity_elapsed = _elapsed_ms(identity_started)
    except Exception as exc:
        return {"ok": False, "state": "network_failure", "identity_authenticated": False,
                "operation_succeeded": False, "room_access": None,
                "http_status": getattr(getattr(exc, "response", None), "status_code", None),
                "elapsed_ms": _elapsed_ms(identity_started), **_network_exception(exc)}

    if me.status_code >= 400:
        if me.status_code == 401:
            failure_state = "authentication_rejected"
        elif me.status_code == 403:
            failure_state = "authorization_denied"
        else:
            failure_state = "identity_check_failed"
        return {"ok": False, "state": failure_state,
                "identity_authenticated": False, "operation_succeeded": False, "room_access": None,
                "status_code": me.status_code, "elapsed_ms": identity_elapsed,
                "error": f"BAND identity check failed: HTTP {me.status_code}"}

    try:
        body = me.json()
        identity = body.get("data", body) if isinstance(body, dict) else None
        if not isinstance(identity, dict):
            raise ValueError("identity object missing")
    except Exception as exc:
        return {"ok": False, "state": "response_error", "identity_authenticated": False,
                "operation_succeeded": False, "room_access": None,
                "status_code": me.status_code, "elapsed_ms": identity_elapsed,
                "exception_class": type(exc).__name__,
                "error_description": "The identity response was not valid JSON in the expected object format.",
                "error": "BAND returned an unreadable identity response."}

    result = {"ok": True, "state": "authentication_succeeded", "identity_authenticated": True,
              "operation_succeeded": False, "operation": "identity_and_room_access_check",
              "status_code": me.status_code, "elapsed_ms": identity_elapsed,
              "agent_id": identity.get("id"), "name": identity.get("name"), "handle": identity.get("handle"),
              "chat_id_present": bool(room), "room_access": None}
    if not room:
        result.update({"room_access_state": "credentials_missing", "room_error": "BAND_CHAT_ID is not configured."})
        result["ok"] = False
        return result

    room_started = time.perf_counter()
    try:
        participants = requests.get(f"{BASE}/chats/{room}/participants", headers=headers, timeout=12)
        room_elapsed = _elapsed_ms(room_started)
    except Exception as exc:
        result.update({"room_access_state": "network_failure", "room_http_status": getattr(getattr(exc, "response", None), "status_code", None),
                       "room_elapsed_ms": _elapsed_ms(room_started), "room_exception_class": type(exc).__name__,
                       "room_error_description": _network_exception(exc)["error_description"],
                       "room_underlying_exception_classes": _network_exception(exc)["underlying_exception_classes"],
                       "room_error": "BAND room access request failed."})
        result["ok"] = False
        return result

    result["participants_status_code"] = participants.status_code
    result["room_elapsed_ms"] = room_elapsed
    result["room_access"] = participants.status_code < 400
    result["room_access_state"] = ("operation_succeeded" if participants.status_code < 400 else
                                   "authentication_rejected" if participants.status_code == 401 else
                                   "authorization_denied" if participants.status_code == 403 else
                                   "room_access_failed")
    result["ok"] = result["room_access"]
    if participants.status_code < 400:
        try:
            participants_body = participants.json()
            people = participants_body.get("data", participants_body.get("participants", [])) if isinstance(participants_body, dict) else []
            result["participant_count"] = len(people) if isinstance(people, list) else None
        except Exception:
            result["participant_count"] = None
    else:
        result["room_error"] = f"BAND room access check failed: HTTP {participants.status_code}"
    return result


def validate_all_identities():
    """Read-only authentication, configured identity comparison, and room checks for each role."""
    _keys, peers, room = _config()
    agents = []
    for role in ROLES:
        check = validate_identity(role)
        expected_id = peers.get(role, {}).get("id")
        actual_id = check.get("agent_id")
        if not check.get("identity_authenticated"):
            identity_match = "not_checked"
        elif not expected_id:
            identity_match = "participant_mapping_missing"
        elif actual_id is None:
            identity_match = "identity_id_not_exposed_by_api"
        else:
            identity_match = "matched" if str(actual_id) == str(expected_id) else "mismatch"

        error_class = None
        if not check.get("identity_authenticated"):
            error_class = check.get("state")
        elif identity_match == "mismatch":
            error_class = "identity_mismatch"
        elif identity_match in ("participant_mapping_missing", "identity_id_not_exposed_by_api"):
            error_class = identity_match
        elif check.get("room_access_state") not in ("operation_succeeded",):
            error_class = check.get("room_access_state") or "room_access_unverified"

        if check.get("identity_authenticated"):
            authentication_status = "succeeded"
        elif check.get("state") == "authentication_rejected":
            authentication_status = "rejected"
        elif check.get("state") == "credentials_missing":
            authentication_status = "not_configured"
        else:
            authentication_status = "not_verified"

        agents.append({
            "role": role,
            "authentication_status": authentication_status,
            "authentication_state": check.get("state"),
            "identity_match_status": identity_match,
            "room_access_status": check.get("room_access_state", "not_checked"),
            "room_access": check.get("room_access"),
            "error_classification": error_class,
            "error": check.get("error") or check.get("room_error"),
            "http_status": check.get("status_code", check.get("http_status")),
            "room_http_status": check.get("participants_status_code"),
            "elapsed_ms": check.get("elapsed_ms"),
            "exception_class": check.get("exception_class"),
            "underlying_exception_classes": check.get("underlying_exception_classes"),
            "error_description": check.get("error_description"),
            "room_elapsed_ms": check.get("room_elapsed_ms"),
            "room_exception_class": check.get("room_exception_class"),
            "room_underlying_exception_classes": check.get("room_underlying_exception_classes"),
            "room_error_description": check.get("room_error_description"),
        })
    return {"operation": "validate_all_band_agents", "messages_sent": False,
            "configured_chat_access_checked": bool(room), "agents": agents,
            "summary": {"total": len(agents),
                        "authenticated": sum(a["authentication_status"] == "succeeded" for a in agents),
                        "room_access": sum(a["room_access_status"] == "operation_succeeded" for a in agents),
                        "identity_matches": sum(a["identity_match_status"] == "matched" for a in agents)}}


def send_handoff(sender, recipient, content):
    keys, peers, room = _config()
    shared_key = os.getenv("BAND_AGENT_API_KEY", "").strip()
    if shared_key:
        if not room:
            return {"sent": False, "processed": False, "state": "credentials_missing", "operation_succeeded": False,
                    "mode": "local", "reason": "Missing BAND_CHAT_ID."}
        return _post_chat_message(shared_key, room, f"MARKETMIND handoff ({sender} to {recipient}): {content}")
    sender_key = keys.get(sender)
    peer = peers.get(recipient) or {}
    if not (room and sender_key and peer.get("id") and peer.get("handle")):
        return {"sent": False, "processed": False, "state": "credentials_missing", "operation_succeeded": False,
                "mode": "local", "reason": "Missing BAND_CHAT_ID, sender key, or recipient participant mapping."}
    handle = str(peer.get("handle", "")).lstrip("@")
    mention = {"id": peer["id"], "name": peer.get("name", recipient), "handle": handle}
    payload = {"message": {"content": f"@{handle} MARKETMIND handoff: {content}", "mentions": [mention]}}
    return _post_chat_message(sender_key, room, payload["message"]["content"], mentions=[mention], recipient=recipient)


def send_test_message():
    """Explicitly submit a harmless test post; never called during startup or analysis."""
    key = os.getenv("BAND_AGENT_API_KEY", "").strip()
    room = os.getenv("BAND_CHAT_ID", "").strip()
    if not key or not room:
        missing = [name for name, value in (("BAND_AGENT_API_KEY", key), ("BAND_CHAT_ID", room)) if not value]
        return {"sent": False, "state": "credentials_missing", "operation_succeeded": False,
                "missing": missing, "error": "Configure the required BAND credentials before sending a test message."}
    return _post_chat_message(key, room, "MARKETMIND BAND connection test. This is an explicit test message.")


def _post_chat_message(api_key, room, content, mentions=None, recipient=None):
    message = {"content": content}
    if mentions:
        message["mentions"] = mentions
    payload = {"message": message}
    try:
        response = requests.post(f"{BASE}/chats/{room}/messages",
                                 headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                                 json=payload, timeout=15)
        if response.status_code >= 400:
            state = "authentication_rejected" if response.status_code in (401, 403) else "operation_failed"
            return {"sent": False, "processed": False, "state": state, "operation_succeeded": False,
                    "mode": "BAND", "status_code": response.status_code,
                    "submission_status": "rejected_by_band",
                    "reason": f"BAND message send failed: HTTP {response.status_code}"}
        body = response.json() if response.content else {}
        return {"sent": True, "processed": False, "state": "operation_succeeded", "operation_succeeded": True,
                "mode": "BAND", "status_code": response.status_code,
                "submission_status": "accepted_by_band", "recipient": recipient,
                "message_id": body.get("data", {}).get("id") if isinstance(body, dict) else None,
                "note": "BAND accepted the message; recipient processing is not confirmed by this send response."}
    except requests.Timeout:
        return {"sent": False, "processed": False, "state": "network_failure", "operation_succeeded": False,
                "mode": "BAND", "submission_status": "unknown_network_failure",
                "reason": "BAND message send timed out"}
    except requests.RequestException:
        return {"sent": False, "processed": False, "state": "network_failure", "operation_succeeded": False,
                "mode": "BAND", "submission_status": "unknown_network_failure",
                "reason": "BAND message send could not reach the service"}
    except Exception as exc:
        return {"sent": False, "processed": False, "state": "response_error", "operation_succeeded": False,
                "mode": "BAND", "submission_status": "unknown_response_error",
                "reason": f"BAND returned an unreadable response ({type(exc).__name__})"}
