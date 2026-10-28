"""Command-line interface: python -m market_intel <command>."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from market_intel import __version__
from market_intel.config import DEMO_DATABASE_URL, ConfigError, Settings, load_settings
from market_intel.database import Database, DatabaseError, parse_database_url
from market_intel.enrich import DEFAULT_ORIGINS, enrich_pending
from market_intel.gemini import GeminiClassifier
from market_intel.http_client import ApiError
from market_intel.logging_setup import LOGGER_NAME, configure_logging, log_event
from market_intel.paths import SAMPLE_CSV, SAMPLE_EXPORT_DIR, resolve_path
from market_intel.pipeline import PipelineError, RunSummary, run_pipeline
from market_intel.reports import export_reports, run_query
from market_intel.sources import SourceError, fetch_remotive, load_csv

logger = logging.getLogger(f"{LOGGER_NAME}.cli")
EXIT_OK, EXIT_FAILURE, EXIT_CONFIG = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-intel", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="load the bundled synthetic sample into a separate demo database")
    demo.add_argument("--reset", action="store_true", help="delete the demo database first")
    demo.add_argument("--ai", action="store_true", help="also label postings with Gemini (needs GEMINI_API_KEY)")

    csv_cmd = commands.add_parser("ingest-csv", help="ingest a local CSV file")
    csv_cmd.add_argument("path", type=Path)
    csv_cmd.add_argument("--origin", choices=("user_csv", "sample"), default="user_csv",
                         help="label stored rows; use 'sample' only for synthetic data")
    csv_cmd.add_argument("--source-name", help="defaults to the file name")
    csv_cmd.add_argument("--ai", action="store_true")

    remotive = commands.add_parser("ingest-remotive", help="fetch live remote jobs from Remotive's public API")
    remotive.add_argument("--category")
    remotive.add_argument("--search")
    remotive.add_argument("--limit", type=int, choices=range(1, 201), metavar="1-200",
                          help="override REMOTIVE_LIMIT")

    enrich = commands.add_parser("enrich", help="label stored postings that have no AI label yet")
    enrich.add_argument("--max-jobs", type=int, help="override GEMINI_MAX_JOBS_PER_RUN")
    enrich.add_argument("--include-live", action="store_true",
                        help="also send live-origin postings to Gemini (check the source's terms first)")

    report = commands.add_parser("report", help="export analytical CSV files and print a summary")
    report.add_argument("--output-dir", type=Path, default=Path("exports/latest"))

    commands.add_parser("init-db", help="create tables if they do not exist")
    commands.add_parser("check-config", help="validate configuration and print it with secrets hidden")
    return parser


def _ai_settings(args, settings: Settings):
    """Return (classifier, max_jobs). Missing AI configuration downgrades to 'no AI' with a warning."""
    if not getattr(args, "ai", False):
        return None, 0
    if not settings.ai_configured:
        log_event(logger, "ai_skipped", logging.WARNING, reason="GEMINI_API_KEY is not set")
        return None, 0
    return GeminiClassifier.from_settings(settings), settings.gemini_max_jobs_per_run


def _print_run(summary: RunSummary, ai_requested: bool) -> None:
    ai_line = f"{summary.ai_enriched} labelled, {summary.ai_failed} failed" if ai_requested else "not requested"
    print(f"Run {summary.run_id}  source={summary.source_name}  data_origin={summary.data_origin}")
    print(f"  rows read:             {summary.rows_read}")
    print(f"  rejected (invalid):    {summary.rows_rejected}")
    print(f"  duplicates in file:    {summary.rows_duplicate_in_batch}")
    print(f"  inserted:              {summary.rows_inserted}")
    print(f"  already stored:        {summary.rows_already_stored}")
    print(f"  AI labels:             {ai_line}")


def _print_summary(db: Database) -> None:
    skills = run_query(db, "skill_demand")
    print("\nTop skills by share of postings (per data_origin):")
    for origin, group in skills.groupby("data_origin"):
        print(f"\n  data_origin = {origin}")
        print(group.head(10)[["skill", "postings", "pct_of_postings"]].to_string(index=False))
    runs = run_query(db, "pipeline_runs")
    print(f"\nPipeline runs recorded: {len(runs)}")


def _cmd_demo(args, settings: Settings) -> int:
    demo_settings = settings.with_database_url(DEMO_DATABASE_URL)
    if args.reset:
        target = parse_database_url(demo_settings.database_url)
        resolve_path(target.location).unlink(missing_ok=True)
    classifier, ai_jobs = _ai_settings(args, demo_settings)
    print("DEMO MODE: synthetic sample data only, stored in the separate demo database.\n")
    with Database(demo_settings.database_url) as db:
        summary = run_pipeline(db, source_name=SAMPLE_CSV.name, data_origin="sample",
                               load=lambda: load_csv(SAMPLE_CSV), classifier=classifier,
                               ai_max_jobs=ai_jobs)
        _print_run(summary, ai_requested=args.ai)
        export_reports(db, SAMPLE_EXPORT_DIR)
        _print_summary(db)
    print(f"\nCSV exports written to {SAMPLE_EXPORT_DIR}")
    return EXIT_OK


def _cmd_ingest_csv(args, settings: Settings) -> int:
    classifier, ai_jobs = _ai_settings(args, settings)
    with Database(settings.database_url) as db:
        summary = run_pipeline(db, source_name=args.source_name or args.path.name,
                               data_origin=args.origin, load=lambda: load_csv(args.path),
                               classifier=classifier, ai_max_jobs=ai_jobs)
    _print_run(summary, ai_requested=args.ai)
    return EXIT_OK


def _cmd_ingest_remotive(args, settings: Settings) -> int:
    with Database(settings.database_url) as db:
        summary = run_pipeline(
            db, source_name="remotive", data_origin="live",
            load=lambda: fetch_remotive(settings, category=args.category, search=args.search,
                                        limit=args.limit))
    _print_run(summary, ai_requested=False)
    print("\nReminder: Remotive requires attribution and a link back to the listing when jobs are shown.")
    return EXIT_OK


def _cmd_enrich(args, settings: Settings) -> int:
    if not settings.ai_configured:
        print("GEMINI_API_KEY is not set, so there is nothing to do. The pipeline works without AI.")
        return EXIT_OK
    origins = (*DEFAULT_ORIGINS, "live") if args.include_live else DEFAULT_ORIGINS
    limit = settings.gemini_max_jobs_per_run if args.max_jobs is None else args.max_jobs
    with Database(settings.database_url) as db:
        db.init_schema()
        result = enrich_pending(db, GeminiClassifier.from_settings(settings), limit, origins)
    print(f"AI labels written: {result.enriched}, failed: {result.failed}"
          + (" (stopped early after repeated failures)" if result.stopped_early else ""))
    return EXIT_OK


def _cmd_report(args, settings: Settings) -> int:
    with Database(settings.database_url) as db:
        db.init_schema()
        export_reports(db, resolve_path(args.output_dir))
        _print_summary(db)
    print(f"\nCSV exports written to {resolve_path(args.output_dir)}")
    return EXIT_OK


def _cmd_init_db(args, settings: Settings) -> int:
    with Database(settings.database_url) as db:
        db.init_schema()
    print("Schema is ready.")
    return EXIT_OK


def _cmd_check_config(args, settings: Settings) -> int:
    print("Configuration is valid:")
    for key, value in settings.describe().items():
        print(f"  {key} = {value}")
    return EXIT_OK


COMMANDS = {"demo": _cmd_demo, "ingest-csv": _cmd_ingest_csv, "ingest-remotive": _cmd_ingest_remotive,
            "enrich": _cmd_enrich, "report": _cmd_report, "init-db": _cmd_init_db,
            "check-config": _cmd_check_config}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return EXIT_CONFIG
    configure_logging(settings.log_level, settings.log_format, settings.secrets())
    try:
        return COMMANDS[args.command](args, settings)
    except (PipelineError, SourceError, ApiError, DatabaseError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
