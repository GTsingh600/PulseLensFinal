"""Cross-platform task runner behind the Makefile.

The team works on Windows, macOS and Linux. Make recipes behave differently under cmd.exe and sh
(venv paths, quoting, `&&`), so every recipe lives here and `make <target>` only calls
`python scripts/dev.py <target>`. Teammates without make can run the same commands directly.

Stdlib only: this runs with whatever Python is on PATH, before the venv exists.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY_VERSION = "3.11"


def run(*cmd: str | Path, check: bool = True) -> int:
    """Run a command from the repo root, echoing it first."""
    args = [str(c) for c in cmd]
    exe = shutil.which(args[0]) or args[0]
    print("$", " ".join(args), flush=True)
    try:
        return subprocess.run([exe, *args[1:]], cwd=ROOT, check=check).returncode
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        return 130


def need_venv() -> None:
    if not VENV_PY.exists():
        sys.exit("No .venv yet. Run `make setup` first.")


def setup(_: argparse.Namespace) -> None:
    # 1. Python venv + server package (editable) with dev tools. uv is preferred because it fetches
    #    Python 3.11 itself; otherwise fall back to the Python running this script.
    if shutil.which("uv"):
        if not VENV_PY.exists():
            run("uv", "venv", "--python", PY_VERSION, VENV)
        run("uv", "pip", "install", "--python", VENV_PY, "-e", "server[dev]")
    else:
        if sys.version_info < (3, 11):  # noqa: UP036 -- runs on the system Python, which may be older
            sys.exit(f"Python {PY_VERSION}+ needed (found {sys.version.split()[0]}); install it or install uv.")
        if not VENV_PY.exists():
            run(sys.executable, "-m", "venv", VENV)
        run(VENV_PY, "-m", "pip", "install", "--upgrade", "pip")
        run(VENV_PY, "-m", "pip", "install", "-e", "server[dev]")

    # 2. Every npm workspace from the lockfile.
    run("npm", "ci")

    # 3. A local .env from the template, so the server starts. Real values are filled in by hand.
    env = ROOT / ".env"
    if not env.exists():
        shutil.copy(ROOT / ".env.example", env)
        print("Created .env from .env.example; replace the change-me values before the demo.")

    # 4. Model files (non-fatal when offline; see the script's summary).
    run(VENV_PY, "scripts/fetch_models.py")


def server(_: argparse.Namespace) -> None:
    need_venv()
    run(VENV_PY, "-m", "uvicorn", "pulselens.api.main:app", "--host", "127.0.0.1", "--port", "8000",
        "--reload", "--reload-dir", "server", check=False)


def lab(_: argparse.Namespace) -> None:
    run("npm", "run", "dev", "-w", "@pulselens/lab", check=False)


def demo(_: argparse.Namespace) -> None:
    run("npm", "run", "dev", "-w", "@pulselens/demo", check=False)


def tunnel(_: argparse.Namespace) -> None:
    """Two cloudflared quick tunnels: phones need HTTPS for the camera and motion sensors."""
    if not shutil.which("cloudflared"):
        sys.exit("cloudflared is not installed: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
    procs = [
        subprocess.Popen([shutil.which("cloudflared"), "tunnel", "--url", f"http://localhost:{port}"], cwd=ROOT)
        for port in (5173, 5174)
    ]
    print("Lab (:5173) and Demo (:5174) tunnels starting; the https://*.trycloudflare.com URLs appear in the log.")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


def test(args: argparse.Namespace) -> None:
    need_venv()
    run(VENV_PY, "-m", "pytest", "server/tests", *args.rest)


def test_web(_: argparse.Namespace) -> None:
    run("npm", "run", "test:web")


def e2e(args: argparse.Namespace) -> None:
    need_venv()
    run("npx", "playwright", "install", "chromium")
    run("npx", "playwright", "test", *args.rest)


def lint(_: argparse.Namespace) -> None:
    need_venv()
    run(VENV_PY, "-m", "ruff", "check", "server", "scripts", "eval")
    run("npm", "run", "lint")


def explainers(_: argparse.Namespace) -> None:
    """Rebuild packages/explain from docs/EXPLAINERS.md."""
    run("node", "--experimental-strip-types", "--disable-warning=ExperimentalWarning", "scripts/build_explainers.ts")


def types(_: argparse.Namespace) -> None:
    """Regenerate packages/types/src/models.gen.ts from server/pulselens/models.py."""
    need_venv()
    run(VENV_PY, "scripts/gen_types.py")


TASKS = {
    "setup": setup, "server": server, "lab": lab, "demo": demo, "tunnel": tunnel,
    "test": test, "test-web": test_web, "e2e": e2e, "lint": lint, "types": types, "explainers": explainers,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=TASKS)
    parser.add_argument("rest", nargs=argparse.REMAINDER, help="extra args passed to pytest / playwright")
    args = parser.parse_args()
    TASKS[args.task](args)


if __name__ == "__main__":
    main()
