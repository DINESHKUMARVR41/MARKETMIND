"""Finch skill-pack integration helpers.
Finch is accessed through its official CLI/Remote MCP workflow; it is not a generic API-key service.
"""
import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def skills_root():
    configured = os.getenv("FINCH_SKILLS_DIR", "").strip()
    return (PROJECT_ROOT / configured).resolve() if configured and not Path(configured).expanduser().is_absolute() else (Path(configured).expanduser() if configured else (PROJECT_ROOT / ".finch" / "skills" if (PROJECT_ROOT / ".finch" / "skills").exists() else PROJECT_ROOT / "finch_skills"))


def load_skill(name):
    candidates = [skills_root() / name / "SKILL.md", Path(__file__).resolve().parents[1] / "skills" / name / "SKILL.md"]
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content, str(path), True
        except OSError:
            pass
    return "", None, False


def status():
    root = skills_root()
    cli = shutil.which("finch")
    skills = {}
    for name in ("market-research", "risk-check"):
        content, path, loaded = load_skill(name)
        skills[name] = {"loaded": loaded, "path": path, "characters": len(content)}
    return {
        "mode": "local Finch-compatible skill packs",
        "skills_directory": str(root),
        "skills": skills,
        "finch_cli_installed": bool(cli),
        "finch_cli_path": cli,
        "remote_mcp_endpoint_configured": bool(os.getenv("FINCH_MCP_URL", "").strip()),
        "remote_mcp_authorization": "not verified by the backend; run the Finch CLI doctor to inspect the local OAuth/MCP session",
        "remote_mcp_url": os.getenv("FINCH_MCP_URL", "https://www.finchtech.ai/mcp"),
        "note": "Local skill loading is verified separately from Finch Remote MCP authorization and marketplace provenance."
    }


def doctor():
    cli = shutil.which("finch")
    if not cli:
        return {"available": False, "ok": False, "state": "cli_missing",
                "remote_authentication": "not_checked", "remote_operation": "not_implemented_in_marketmind",
                "message": "Finch CLI not installed on this machine"}
    try:
        result = subprocess.run([cli, "mcp", "doctor"], capture_output=True, text=True, timeout=30, check=False)
        return {"available": True, "ok": result.returncode == 0,
                "state": "local_doctor_succeeded" if result.returncode == 0 else "local_doctor_failed",
                "remote_authentication": "not_confirmed_by_marketmind",
                "remote_operation": "not_implemented_in_marketmind",
                "return_code": result.returncode,
                # CLI diagnostics can print sensitive environment/configuration; don't return them.
                "output_suppressed": True}
    except subprocess.TimeoutExpired:
        return {"available": True, "ok": False, "state": "local_doctor_timeout",
                "remote_authentication": "not_checked", "remote_operation": "not_implemented_in_marketmind",
                "message": "Finch CLI doctor timed out"}
    except Exception as exc:
        return {"available": True, "ok": False, "state": "local_doctor_failed",
                "remote_authentication": "not_checked", "remote_operation": "not_implemented_in_marketmind",
                "message": f"Finch CLI doctor could not run ({type(exc).__name__})"}
