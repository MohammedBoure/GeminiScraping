#!/usr/bin/env python3
import sys
import os
import json
import asyncio
import argparse
import logging
from typing import Optional

# Ensure UTF-8 output encoding across Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

from core.job_manager import JobManager
from core.worker import WorkerPool, generate_oneshot


def setup_logging(is_json: bool = False, verbose: bool = False):
    """
    Configures logging. If JSON output is requested, stream logs to stderr
    to keep stdout completely clean for JSON parsing.
    """
    level = logging.DEBUG if verbose else logging.INFO
    log_stream = sys.stderr if is_json else sys.stdout
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=log_stream
    )
    # Silence noisy third-party loggers
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def cmd_submit(args):
    setup_logging(is_json=args.json)
    jm = JobManager()
    job = jm.add_job(prompt=args.prompt, filename=args.filename)

    output_data = {
        "job_id": job["job_id"],
        "status": job["status"],
        "output_path": job["output_path"],
        "prompt": job["prompt"]
    }

    if args.json:
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
    else:
        print(f"[✓] Job submitted successfully!")
        print(f"    Job ID:      {job['job_id']}")
        print(f"    Status:      {job['status']}")
        print(f"    Output Path: {job['output_path']}")
        print(f"    Prompt:      {job['prompt']}")


def cmd_status(args):
    setup_logging(is_json=args.json)
    jm = JobManager()
    job = jm.get_job(args.job_id)

    if not job:
        error_payload = {"error": f"Job '{args.job_id}' not found."}
        if args.json:
            print(json.dumps(error_payload, ensure_ascii=False, indent=2))
        else:
            print(f"[✗] Error: Job '{args.job_id}' not found.")
        sys.exit(1)

    if args.json:
        print(json.dumps(job, ensure_ascii=False, indent=2))
    else:
        print(f"Job Details for {job['job_id']}:")
        print(f"  Status:       {job.get('status')}")
        print(f"  Created At:   {job.get('created_at')}")
        print(f"  Started At:   {job.get('started_at')}")
        print(f"  Completed At: {job.get('completed_at')}")
        print(f"  Output Path:  {job.get('output_path')}")
        print(f"  Prompt:       {job.get('prompt')}")
        if job.get("error"):
            print(f"  Error:        {job.get('error')}")


def cmd_list(args):
    setup_logging(is_json=args.json)
    jm = JobManager()
    jobs = jm.list_jobs(status=args.status)

    if args.json:
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
    else:
        status_label = f"[{args.status.upper()}]" if args.status else "[ALL]"
        print(f"=== Jobs List {status_label} (Count: {len(jobs)}) ===")
        if not jobs:
            print("  (No jobs found)")
            return

        for j in jobs:
            err = f" | Err: {j['error']}" if j.get("error") else ""
            print(f"  - {j['job_id']} | Status: {j['status']:<11} | File: {j['filename']}{err}")


def cmd_start_worker(args):
    setup_logging(is_json=False, verbose=args.verbose)
    pool = WorkerPool(max_tabs=args.max_tabs, timeout=args.timeout)

    try:
        asyncio.run(pool.run())
    except KeyboardInterrupt:
        print("\n[!] Received shutdown signal. Terminating workers...")
        pool.stop()


def cmd_generate(args):
    setup_logging(is_json=args.json, verbose=args.verbose)
    try:
        result = asyncio.run(generate_oneshot(
            prompt=args.prompt,
            output_path=args.output,
            timeout=args.timeout
        ))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[✓] Video generated successfully!")
            print(f"    Job ID:      {result.get('job_id')}")
            print(f"    Output Path: {result.get('output_path')}")
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e), "status": "failed"}, ensure_ascii=False, indent=2))
        else:
            print(f"[✗] Generation failed: {e}")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Asynchronous multi-tab Gemini video generation worker & queue CLI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    # submit
    p_submit = subparsers.add_parser("submit", help="Enqueue a new video generation job.")
    p_submit.add_argument("--prompt", "-p", required=True, type=str, help="Text prompt for video generation.")
    p_submit.add_argument("--filename", "-f", type=str, default=None, help="Optional custom output filename (e.g. intro.mp4).")
    p_submit.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    p_submit.set_defaults(func=cmd_submit)

    # status
    p_status = subparsers.add_parser("status", help="Get details and status of a specific job.")
    p_status.add_argument("job_id", type=str, help="The job ID to inspect.")
    p_status.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    p_status.set_defaults(func=cmd_status)

    # list
    p_list = subparsers.add_parser("list", help="List all jobs with optional status filter.")
    p_list.add_argument("--status", choices=["pending", "processing", "completed", "failed"], help="Filter by status.")
    p_list.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    p_list.set_defaults(func=cmd_list)

    # start-worker
    p_worker = subparsers.add_parser("start-worker", help="Start the asynchronous multi-tab background worker.")
    p_worker.add_argument("--max-tabs", type=int, default=3, help="Maximum concurrent browser tabs (default: 3).")
    p_worker.add_argument("--timeout", type=int, default=360, help="Per-video generation timeout in seconds (default: 360).")
    p_worker.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging.")
    p_worker.set_defaults(func=cmd_start_worker)

    # generate
    p_gen = subparsers.add_parser("generate", help="One-shot blocking video generation.")
    p_gen.add_argument("--prompt", "-p", required=True, type=str, help="Text prompt for video generation.")
    p_gen.add_argument("--output", "-o", type=str, default=None, help="Target output file path.")
    p_gen.add_argument("--timeout", type=int, default=360, help="Per-video generation timeout in seconds (default: 360).")
    p_gen.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging.")
    p_gen.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    p_gen.set_defaults(func=cmd_generate)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
