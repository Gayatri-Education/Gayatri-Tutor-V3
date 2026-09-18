"""Gayatri AI — Nightly Mastery & Progress Report Generator (Sec 9 & 10).

Rolls up student diagnostic attempts, practice attempts, and BKT topic mastery
into teacher/parent reports exported in both CSV and JSON formats.

Usage:
    python scripts/nightly_mastery_report.py
    python scripts/nightly_mastery_report.py --student student-1
    python scripts/nightly_mastery_report.py --output-dir data/reports/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import DATA_DIR
from core.tutor.course_repo import course_repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nightly_mastery_report")


def generate_mastery_summary(target_student_id: str | None = None) -> dict:
    """Aggregate student topic mastery and question attempts into structured report metrics."""
    conn = course_repo.conn
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "total_records": 0,
        "students": {},
        "records": [],
    }

    # 1. Fetch all mastery rows
    query = """
        SELECT m.student_id, m.topic_id, m.mastery_score, m.confidence, m.last_updated,
               t.title AS topic_title, t.course_id, c.subject, c.grade
        FROM k12_topic_mastery m
        LEFT JOIN k12_topics t ON m.topic_id = t.id
        LEFT JOIN k12_courses c ON t.course_id = c.id
    """
    params = []
    if target_student_id:
        query += " WHERE m.student_id = ?"
        params.append(target_student_id)
    query += " ORDER BY m.student_id, c.grade, c.subject, m.topic_id;"

    with course_repo._lock:
        rows = conn.execute(query, params).fetchall()

    for r in rows:
        st_id = r["student_id"]
        top_id = r["topic_id"]
        mastery = float(r["mastery_score"])

        # Fetch attempt stats for this student & topic
        stats_query = """
            SELECT COUNT(*) AS total_attempts,
                   SUM(is_correct) AS correct_attempts,
                   AVG(response_time_ms) AS avg_response_time
            FROM k12_diagnostic_attempts
            WHERE student_id = ? AND topic_id = ?;
        """
        with course_repo._lock:
            stats = conn.execute(stats_query, (st_id, top_id)).fetchone()

        total_att = stats["total_attempts"] if stats and stats["total_attempts"] else 0
        correct_att = stats["correct_attempts"] if stats and stats["correct_attempts"] else 0
        avg_resp = round(stats["avg_response_time"] or 0, 1) if stats else 0
        accuracy = round((correct_att / total_att * 100), 1) if total_att > 0 else 0.0

        if mastery < 0.40:
            tier = "Remedial"
        elif mastery < 0.70:
            tier = "Core"
        else:
            tier = "Advanced"

        last_active = datetime.fromtimestamp(r["last_updated"]).strftime("%Y-%m-%d %H:%M") if r["last_updated"] else "N/A"

        record = {
            "student_id": st_id,
            "course_id": r["course_id"] or "unknown",
            "subject": r["subject"] or "General",
            "grade": r["grade"] or 0,
            "topic_id": top_id,
            "topic_title": r["topic_title"] or top_id,
            "mastery_score": round(mastery, 3),
            "mastery_percent": f"{round(mastery * 100, 1)}%",
            "tier": tier,
            "total_attempts": total_att,
            "correct_attempts": correct_att,
            "accuracy_percent": f"{accuracy}%",
            "avg_response_time_ms": avg_resp,
            "last_active": last_active,
        }
        report_data["records"].append(record)

        # Aggregate student-level rollups
        if st_id not in report_data["students"]:
            report_data["students"][st_id] = {
                "topics_tracked": 0,
                "topics_mastered": 0,
                "topics_remedial": 0,
                "total_attempts": 0,
                "correct_attempts": 0,
            }
        st_summary = report_data["students"][st_id]
        st_summary["topics_tracked"] += 1
        if tier == "Advanced":
            st_summary["topics_mastered"] += 1
        elif tier == "Remedial":
            st_summary["topics_remedial"] += 1
        st_summary["total_attempts"] += total_att
        st_summary["correct_attempts"] += correct_att

    report_data["total_records"] = len(report_data["records"])
    return report_data


def export_reports(report_data: dict, output_dir: Path) -> tuple[Path, Path]:
    """Export the report data to CSV and JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"mastery_report_{date_tag}.json"
    csv_path = output_dir / f"mastery_report_{date_tag}.csv"

    # Export JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # Export CSV
    records = report_data.get("records", [])
    if records:
        fieldnames = list(records[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
    else:
        # Write empty CSV header
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            f.write("student_id,course_id,subject,grade,topic_id,topic_title,mastery_score,tier\n")

    return json_path, csv_path


def print_ascii_summary(report_data: dict):
    """Print a clean ASCII summary table to console for teachers/admins."""
    records = report_data.get("records", [])
    print("\n" + "=" * 80)
    print(" [*] GAYATRI TUTOR -- K-12 STUDENT MASTERY & PROGRESS REPORT")
    print(" Generated: " + report_data["generated_at"])
    print("=" * 80)

    if not records:
        print(" No mastery or practice records found yet.")
        print(" Students will appear here once they take diagnostics or answer questions.")
        print("=" * 80 + "\n")
        return

    print(f" {'STUDENT':<12} | {'SUBJECT':<12} | {'TOPIC':<24} | {'MASTERY':<8} | {'TIER':<9} | {'ACCURACY'}")
    print("-" * 80)
    for r in records:
        top_name = r["topic_title"][:22] + ".." if len(r["topic_title"]) > 24 else r["topic_title"]
        print(
            f" {r['student_id']:<12} | {r['subject']:<12} | {top_name:<24} | "
            f"{r['mastery_percent']:<8} | {r['tier']:<9} | {r['accuracy_percent']} ({r['correct_attempts']}/{r['total_attempts']})"
        )
    print("=" * 80)

    for st_id, s in report_data.get("students", {}).items():
        overall_acc = round(s["correct_attempts"] / s["total_attempts"] * 100, 1) if s["total_attempts"] > 0 else 0
        print(
            f" [Summary: {st_id}] Tracked Topics: {s['topics_tracked']} | "
            f"Mastered: {s['topics_mastered']} | Remedial: {s['topics_remedial']} | "
            f"Overall Accuracy: {overall_acc}%"
        )
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate K-12 Student Mastery & Progress Reports.")
    parser.add_argument("--student", type=str, default=None, help="Filter report by student ID")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DATA_DIR / "reports"),
        help="Directory to save generated CSV and JSON reports",
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    logger.info("Generating student mastery rollup report...")

    report = generate_mastery_summary(target_student_id=args.student)
    print_ascii_summary(report)

    json_file, csv_file = export_reports(report, out_path)
    logger.info(f"✓ JSON Report exported: {json_file}")
    logger.info(f"✓ CSV Report exported:  {csv_file}")


if __name__ == "__main__":
    main()
