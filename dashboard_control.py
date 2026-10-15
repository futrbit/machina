from __future__ import annotations

import os
import sys
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
PIPELINES = ROOT / "pipelines"
LOG_DIR = ROOT / "data" / "dashboard_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

dashboard_bp = Blueprint("machina_dashboard", __name__)
LOCK = threading.RLock()
JOBS = {}

SCRIPT_GROUPS = [
    {
        "name": "Intelligence & Investigation",
        "scripts": [
            "deep_source_fetcher.py",
            "entity_intelligence_builder.py",
            "specialist_indexer.py",
            "investigative_reporter.py",
            "deep_researcher.py",
            "evidence_retriever.py",
        ],
    },
    {
        "name": "Story Selection & Editorial",
        "scripts": [
            "editorial_formatter.py",
            "five_journalists.py",
            "story_hunter.py",
            "editorial_engine.py",
            "editorial_agents.py",
        ],
    },
    {
        "name": "Editorial & Weekly",
        "scripts": [
            "specialist_editorial.py",
            "weekly.py",
        ],
    },
    {
        "name": "Daily Briefing & Newsroom",
        "scripts": [
            "local_newsroom.py",
            "five_more_journalists.py",
            "news_fetcher.py",
            "rewriter.py",
        ],
    },
]

ALLOWED = {
    name
    for group in SCRIPT_GROUPS
    for name in group["scripts"]
}


@dashboard_bp.before_request
def local_only():
    if request.remote_addr not in {"127.0.0.1", "::1", "localhost"}:
        abort(403)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def refresh(job):
    process = job.get("_process")

    if process is not None:
        code = process.poll()

        if code is not None and job["status"] in {"running", "stopping"}:
            job["status"] = "finished" if code == 0 else "failed"
            job["return_code"] = code
            job["finished_at"] = now()
            job["_process"] = None

    return job


def public(job):
    return {
        key: value
        for key, value in job.items()
        if not key.startswith("_")
    }


@dashboard_bp.get("/dashboard")
def dashboard_page():
    return send_from_directory(ROOT / "frontend", "dashboard.html")


@dashboard_bp.get("/dashboard/api/scripts")
def dashboard_scripts():
    return jsonify({"groups": SCRIPT_GROUPS})


@dashboard_bp.get("/dashboard/api/health")
def dashboard_health():
    return jsonify({
        "status": "ok",
        "python": sys.version.split()[0],
        "pipeline_files_found": sum(
            (PIPELINES / name).is_file() for name in ALLOWED
        ),
        "pipeline_files_allowed": len(ALLOWED),
    })


@dashboard_bp.get("/dashboard/api/status")
def dashboard_status():
    with LOCK:
        return jsonify({
            "jobs": {
                name: public(refresh(job))
                for name, job in JOBS.items()
            }
        })


@dashboard_bp.post("/dashboard/api/run")
def dashboard_run():
    body = request.get_json(silent=True) or {}
    name = body.get("script", "")

    if name not in ALLOWED:
        return jsonify({
            "error": "That script is not on the approved list."
        }), 400

    path = (PIPELINES / name).resolve()

    if path.parent != PIPELINES.resolve() or not path.is_file():
        return jsonify({
            "error": f"Pipeline file not found: {name}"
        }), 404

    with LOCK:
        previous = JOBS.get(name)

        if previous:
            refresh(previous)

            if previous["status"] in {"running", "stopping"}:
                return jsonify({
                    "error": "This pipeline is already running."
                }), 409

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"{Path(name).stem}_{stamp}.log"

        try:
            with log_path.open(
                "a", encoding="utf-8", errors="replace"
            ) as log:
                log.write(
                    f"=== Dashboard run: {name} | {now()} ===\n"
                )
                log.flush()

                process = subprocess.Popen(
                    [sys.executable, "-u", str(path)],
                    cwd=str(ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        if os.name == "nt" else 0
                    ),
                )

        except Exception as exc:
            return jsonify({
                "error": f"Could not start pipeline: {exc}"
            }), 500

        JOBS[name] = {
            "script": name,
            "status": "running",
            "pid": process.pid,
            "started_at": now(),
            "finished_at": None,
            "return_code": None,
            "log_file": str(
                log_path.relative_to(ROOT)
            ).replace("\\", "/"),
            "_process": process,
        }

        return jsonify({"job": public(JOBS[name])}), 201


@dashboard_bp.post("/dashboard/api/stop")
def dashboard_stop():
    body = request.get_json(silent=True) or {}
    name = body.get("script", "")

    with LOCK:
        job = JOBS.get(name)

        if not job:
            return jsonify({
                "error": "No recorded run for that pipeline."
            }), 404

        refresh(job)
        process = job.get("_process")

        if not process or job["status"] != "running":
            return jsonify({
                "error": "That pipeline is not running."
            }), 409

        try:
            process.terminate()
            job["status"] = "stopping"
            return jsonify({"job": public(job)})

        except Exception as exc:
            return jsonify({
                "error": f"Could not stop pipeline: {exc}"
            }), 500


@dashboard_bp.get("/dashboard/api/logs")
def dashboard_logs():
    name = request.args.get("script", "")

    if name not in ALLOWED:
        return jsonify({"error": "Unknown pipeline."}), 400

    with LOCK:
        job = JOBS.get(name)

        if not job:
            return jsonify({
                "script": name,
                "status": "not_started",
                "lines": [],
            })

        refresh(job)

        try:
            with (
                ROOT / job["log_file"]
            ).open(
                "r", encoding="utf-8", errors="replace"
            ) as handle:
                lines = handle.readlines()[-180:]

        except OSError:
            lines = ["Log file is not available yet.\n"]

        return jsonify({
            "script": name,
            "status": job["status"],
            "lines": lines,
        })

