import sqlite3
from flask import jsonify, request

def install_metric_facts_api(research_bp, root):
    @research_bp.get("/dashboard/api/research/metric-facts")
    def metric_facts_api():
        sector = (request.args.get("sector") or "").strip().lower()
        allowed = {"drones", "robotics", "autonomous", "ai"}

        if sector not in allowed:
            return jsonify({"error": "Choose drones, robotics, autonomous, or ai"}), 400

        db = root / "data" / "intelligence" / "sector_metrics.sqlite3"
        if not db.exists():
            return jsonify({"error": "Metric facts database has not been created"}), 503

        try:
            con = sqlite3.connect(
                f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5
            )
            con.row_factory = sqlite3.Row
            table = con.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'metric_facts'
            """).fetchone()

            if not table:
                con.close()
                return jsonify({"error": "Metric facts table not found"}), 503

            rows = con.execute("""
                SELECT metric_name, value, unit, evidence_sentence, title,
                       source_name, published, source_url, status
                FROM metric_facts
                WHERE sector = ?
                ORDER BY
    CASE
        WHEN sector = 'ai' AND metric_name = 'Model parameters' THEN 1
        ELSE 0
    END,
    published DESC,
    metric_name ASC
LIMIT 100
            """, (sector,)).fetchall()
            con.close()

            facts = [dict(row) for row in rows]
            return jsonify({
                "sector": sector,
                "count": len(facts),
                "status": "SOURCE_REPORTED_UNVERIFIED",
                "note": (
                    "Extracted from indexed text. Verify the original source, "
                    "measurement conditions, and applicability before relying on it."
                ),
                "facts": facts
            })
        except sqlite3.Error:
            return jsonify({"error": "Could not read extracted metric facts"}), 503
