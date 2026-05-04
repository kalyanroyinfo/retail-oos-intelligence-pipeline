#!/usr/bin/env python3
"""Bootstrap + launch the Streamlit dashboard locally.

Reads Azure SQL credentials directly from `notebooks/config/pipeline_config.py`
(the same file Databricks uses), so there's a single source of truth for
host/db/user/password.  No `.env` file involved.

Usage:
    python3 scripts/run_dashboard.py            # install into current Python, run
    python3 scripts/run_dashboard.py --venv     # create/reuse .venv first (recommended)
    python3 scripts/run_dashboard.py --no-install   # skip pip; just launch

⚠️  Don't commit `pipeline_config.py` with real credentials.  Edit it
locally to test, then revert (or edit on Databricks only).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
REQS        = REPO_ROOT / "dashboards" / "requirements.txt"
APP         = REPO_ROOT / "dashboards" / "streamlit_app.py"
CONFIG_FILE = REPO_ROOT / "notebooks" / "config" / "pipeline_config.py"
VENV_DIR    = REPO_ROOT / ".venv"

# Constants we forward from pipeline_config.py to the Streamlit process.
# `streamlit_app.py` reads these via os.getenv(...).
FORWARDED_KEYS = ("AZSQL_HOST", "AZSQL_DB", "AZSQL_TABLE", "AZSQL_USER", "AZSQL_PASSWORD")
PLACEHOLDER    = "REPLACE_ME"


def load_pipeline_config() -> dict[str, str]:
    """Import pipeline_config.py and pull the AZSQL_* constants out.

    The file has Databricks `# COMMAND ----------` separators but no
    `dbutils`/`spark` references in the constants block, so plain Python
    importlib loads it cleanly.
    """
    if not CONFIG_FILE.exists():
        sys.exit(f"!! cannot find {CONFIG_FILE}")

    spec = importlib.util.spec_from_file_location("pipeline_config", CONFIG_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    out: dict[str, str] = {}
    for key in FORWARDED_KEYS:
        if not hasattr(module, key):
            continue
        out[key] = str(getattr(module, key))
    return out


def python_for_run(use_venv: bool) -> Path:
    """Resolve the Python interpreter to use for installs + the streamlit launch."""
    if not use_venv:
        return Path(sys.executable)

    if not VENV_DIR.exists():
        print(f"-> creating venv at {VENV_DIR}")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])

    py = VENV_DIR / "bin" / "python"
    if not py.exists():                     # Windows layout
        py = VENV_DIR / "Scripts" / "python.exe"
    return py


def streamlit_importable(python: Path) -> bool:
    return subprocess.call(
        [str(python), "-c", "import streamlit"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) == 0


def install_requirements(python: Path) -> None:
    print(f"-> upgrading pip ({python})")
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    print(f"-> installing {REQS.name}")
    subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(REQS)])


def launch_streamlit(python: Path, extra_env: dict[str, str]) -> None:
    env = {**os.environ, **extra_env}
    args = [str(python), "-m", "streamlit", "run", str(APP)]
    print(f"-> launching: {' '.join(args)}")
    os.execvpe(str(python), args, env)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--venv",       action="store_true",
                        help="Create/reuse .venv at the repo root for isolation.")
    parser.add_argument("--no-install", action="store_true",
                        help="Skip pip install; assume deps are already present.")
    args = parser.parse_args()

    python = python_for_run(args.venv)

    if not streamlit_importable(python):
        if args.no_install:
            sys.exit(f"streamlit not importable in {python} and --no-install was passed.")
        install_requirements(python)
    else:
        print(f"-> streamlit already importable in {python}, skipping install")

    cfg = load_pipeline_config()
    if not cfg:
        sys.exit(f"!! no AZSQL_* keys found in {CONFIG_FILE.name}")

    # Warn (but don't block) if the placeholder values are still in place.
    placeholders = [k for k, v in cfg.items() if v.startswith(PLACEHOLDER)]
    if placeholders:
        print(f"!! warning: still placeholders in pipeline_config.py: {', '.join(placeholders)}")
        print(f"!! the dashboard will fail to connect — edit pipeline_config.py and re-run.")

    print(f"-> loaded from {CONFIG_FILE.name}: {', '.join(sorted(cfg))}")
    launch_streamlit(python, cfg)


if __name__ == "__main__":
    main()
