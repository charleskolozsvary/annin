import csv
import json
import re
import subprocess
import time

from datetime import datetime
from pathlib import Path

REALWORLD_DIR = Path("real_world")
RESULTS_DIR = Path("results")

PDF_RE = re.compile(r"^ann.*\.pdf$")

SUMMARY_RE = re.compile(
    r"n_annots:\s*(\d+),\s*"
    r"n_edits:\s*(\d+),\s*"
    r"n_corrs:\s*(\d+),\s*"
    r"n_autos:\s*(\d+)"
)

CSV_COLUMNS = [
    "failed",
    "log_exists",
    "n_annots",
    "n_edits",
    "n_corrs",
    "n_autos",
    "id",    
    "runtime",
]

def discover_jobs():
    jobs = []
    for article_dir in sorted(REALWORLD_DIR.iterdir()):
        if not article_dir.is_dir():
            continue
        tex_file = article_dir / "source.tex"

        if not tex_file.exists():
            print(f"ERROR: missing source.tex in {article_dir}", flush=True)
            continue

        pdfs = [
            p for p in article_dir.iterdir()
            if p.is_file() and PDF_RE.match(p.name)
        ]

        if not pdfs:
            continue

        for pdf in sorted(pdfs):
            jobs.append((article_dir, pdf, tex_file))
    return jobs

def parse_log(log_path: Path):
    with open(log_path, 'r') as f:
        for line in f:
            m = SUMMARY_RE.search(line)
            if m:
                return tuple(int(x) for x in m.groups())
    raise RuntimeError(f"Could not find summary line in {log_path}")

def make_row_id(article_dir: Path, pdf_file: Path):
    return f'{article_dir.stem}_{pdf_file.stem}'

def run_job(job):
    article_dir, pdf_file, tex_file = job
    start = time.perf_counter()
    command = [
        "annin",
        "-a",
        '--no-svn',
        '--no-replace',
        pdf_file.name,
        tex_file.name,
    ]
    command_str = ' '.join(command)
    print(f'Running {article_dir.name}, {pdf_file.name}...', flush = True)
    result = subprocess.run(
        command,
        cwd=article_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    runtime = time.perf_counter() - start
    failed = int(result.returncode != 0)
    log_path = article_dir / f"annin_{pdf_file.stem}.log"
    log_exists = int(log_path.exists())
    n_annots = n_edits = n_corrs = n_autos = 0
    
    if log_exists:
        n_annots, n_edits, n_corrs, n_autos = parse_log(log_path)
        
    row_id = make_row_id(article_dir, pdf_file)
    values = {
        'failed': failed,
        'log_exists': log_exists,
        'n_annots': n_annots,
        'n_edits': n_edits,
        'n_corrs': n_corrs,
        'n_autos': n_autos,
        'id': row_id,        
        'runtime': round(runtime, 3),
    }
    return {
        field : values[field]
        for field in CSV_COLUMNS
    }

def write_csv(rows):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d_%H-%M")
    csv_path = RESULTS_DIR / f"realworld_results_{timestamp}.csv"    
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path

def generate_realworld_results():
    jobs = discover_jobs()
    if not jobs:
        raise RuntimeError(f"No realworld regression jobs found in {REALWORLD_DIR}")
    rows = []
    for job in jobs:
        try:
            rows.append(run_job(job))
        except Exception as e:
            article_dir, pdf_file, _ = job
            row_id = make_row_id(article_dir, pdf_file)
            # it's possible that annin ran but we could not successfully
            # parse the log, but I don't care about distinguishing such cases
            # The log should always be parseable. We get the relevant error message
            # either way
            print(
                f"ERROR processing {pdf_file}, {article_dir}: {e}",
                flush=True,
            )
            fail_vals = {
                'failed': 1, 
                'log_exists': 0, 
                'n_annots': 0, 
                'n_edits': 0, 
                'n_corrs': 0, 
                'n_autos': 0, 
                'id': row_id,
                'runtime': 0.0, 
            }

            rows.append({
                field : fail_vals[field] for field in CSV_COLUMNS
            })
    rows.sort(key=lambda r: r["id"])
    csv_path = write_csv(rows)
    print(f"Wrote CSV: {csv_path}")
    return csv_path

if __name__ == "__main__":
    generate_realworld_results()
