from flask import jsonify
import sqlite3
import re

SECTOR_PROFILES = {
    "drones": {
        "label": "Drones",
        "terms": ["drone", "uav", "quadrotor", "unmanned aerial", "aerial robot"],
        "metrics": [
            ("Flight endurance & battery", ["flight time", "endurance", "battery energy", "battery capacity"]),
            ("Speed & operating range", ["maximum speed", "cruise speed", "flight range", "operating range"]),
            ("Payload & deployment", ["payload capacity", "payload", "deployment time"]),
            ("Charging & operating cost", ["charging time", "cost per flight", "operating cost"]),
            ("Drone shows & swarms", ["drone show", "drone swarm", "synchronisation", "synchronization", "fleet size"]),
        ],
    },
    "robotics": {
        "label": "Robotics",
        "terms": ["robot", "robotics", "robotic arm", "manipulator", "humanoid"],
        "metrics": [
            ("Payload & reach", ["payload", "reach", "load capacity"]),
            ("Cycle time & repeatability", ["cycle time", "repeatability", "positioning accuracy"]),
            ("Operating hours & energy", ["operating hours", "energy consumption", "battery life"]),
            ("Purchase & task cost", ["purchase cost", "cost per task", "total cost of ownership"]),
        ],
    },
    "autonomous": {
        "label": "Autonomous systems",
        "terms": ["autonomous vehicle", "self-driving", "driverless", "autonomous system", "adas"],
        "metrics": [
            ("Operating conditions", ["operating conditions", "weather conditions", "operational design domain"]),
            ("Interventions & test distance", ["human intervention", "disengagement", "miles driven", "kilometres driven", "kilometers driven"]),
            ("Safety & independent assessment", ["safety assessment", "safety incident", "independent assessment"]),
            ("Regulation & deployment", ["regulatory approval", "deployment location", "approved for deployment"]),
        ],
    },
    "ai": {
        "label": "AI",
        "terms": ["large language model", "llm", "generative ai", "foundation model", "ai model", "inference"],
        "metrics": [
            ("Benchmarks & evaluation", ["benchmark", "evaluation dataset", "evaluation date", "score"]),
            ("Latency & throughput", ["latency", "throughput", "tokens per second", "time to first token"]),
            ("Token & inference cost", ["cost per million tokens", "inference cost", "input token price", "output token price"]),
            ("Context & modalities", ["context window", "multimodal", "image input", "audio input", "video input"]),
            ("Hardware & energy", ["gpu", "hardware requirements", "energy consumption", "power consumption"]),
        ],
    },
}

def install_sector_intelligence_route(research_bp, root):
    @research_bp.get("/dashboard/api/research/sector-intelligence")
    def sector_intelligence():
        db = root / "data" / "intelligence" / "deep_raw_index.sqlite3"
        if not db.exists():
            return jsonify({"error": "Research index database not found"}), 503

        try:
            connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""
                SELECT paper_id, title, summary, sectors, source_name, url, published
                FROM papers
            """).fetchall()
            connection.close()
        except (sqlite3.Error, OSError):
            return jsonify({"error": "Could not read the research index"}), 503

        records = []
        for row in rows:
            item = dict(row)
            item["_text"] = " ".join(str(item.get(k) or "") for k in
                ("title", "summary", "sectors", "source_name")).lower()
            records.append(item)

        output = {"record_count": len(records), "measurement_warning":
            "Counts show matching research records, not verified real-world specifications.",
            "sectors": {}}

        for key, profile in SECTOR_PROFILES.items():
            sector_records = [r for r in records if any(t in r["_text"] for t in profile["terms"])]
            metrics = []
            for name, terms in profile["metrics"]:
                hits = [r for r in sector_records if any(t in r["_text"] for t in terms)]
                sample = []
                for r in hits[:4]:
                    sample.append({k: r.get(k) for k in
                        ("paper_id", "title", "summary", "source_name", "url", "published", "sectors")})
                metrics.append({"name": name, "record_matches": len(hits), "status":
                    "EVIDENCE TO REVIEW" if hits else "NO MATCHING RECORDS FOUND",
                    "evidence": sample})
            output["sectors"][key] = {
                "label": profile["label"],
                "sector_record_matches": len(sector_records),
                "metrics": metrics
            }

        return jsonify(output)
