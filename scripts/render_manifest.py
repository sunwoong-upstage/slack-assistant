from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "app_manifest.yaml"


def main() -> None:
    app_base_url = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if not app_base_url:
        raise SystemExit("APP_BASE_URL is required")

    content = TEMPLATE_PATH.read_text()
    rendered = content.replace("__APP_BASE_URL__", app_base_url)
    rendered_lines = [
        line for line in rendered.splitlines() if not line.lstrip().startswith("#")
    ]
    rendered = "\n".join(rendered_lines).strip() + "\n"
    sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
