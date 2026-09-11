import argparse
import json
import os
from pathlib import Path
from typing import Mapping


EXCLUDES = [
    ".git",
    ".gitignore",
    ".env",
    "**/__pycache__",
    "**/*.pyc",
    "tests/**",
    "scripts/**",
    ".pytest_cache/**",
    "*.md",
    "infra/**",
    ".terraform/**",
    "*.csv",
    "*.xlsx",
    "*.txt",
    "key.json",
    ".DS_Store",
    ".vscode/**",
    ".idea/**",
    "db.sqlite3",
    "cache/**",
    "data/**",
    "media/**",
    "venv/**",
    ".venv/**",
    "manage.py",
    "docker-compose*.yml",
]


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"Required deployment setting {name} is missing")
    return value


def patch_settings(config: dict, environment: Mapping[str, str]) -> dict:
    stage = environment.get("ZAPPA_STAGE", "production").strip() or "production"
    if stage not in config:
        raise ValueError(f"Zappa stage {stage!r} does not exist")

    stage_config = config[stage]
    stage_config.update(
        project_name="portfolio",
        runtime="python3.11",
        slim_handler=True,
        use_precompiled_packages=False,
        log_level="WARNING",
        ephemeral_storage={"Size": 3072},
        # API Gateway REST caps at 29 s; keep Lambda timeout aligned.
        timeout_seconds=30,
        memory_size=1536,
        exclude=EXCLUDES,
    )

    role_arn = environment.get("TF_ROLE_ARN", "").strip() or stage_config.get("role_arn", "")
    bucket = environment.get("TF_S3_BUCKET", "").strip() or stage_config.get("s3_bucket", "")
    if not role_arn or not bucket:
        raise ValueError("Zappa role_arn and s3_bucket must be configured")
    stage_config["role_arn"] = role_arn
    stage_config["s3_bucket"] = bucket

    layer_arns = environment.get("LAMBDA_LAYER_ARNS", "").strip()
    stage_config["lambda_layers"] = (
        [item.strip() for item in layer_arns.split(",") if item.strip()]
        if layer_arns
        else []
    )

    access_mode = _required(environment, "CLOUDFLARE_ACCESS_ENABLED").lower()
    if access_mode not in {"true", "false"}:
        raise ValueError("CLOUDFLARE_ACCESS_ENABLED must be true or false")

    variables = stage_config.setdefault("environment_variables", {})
    variables.pop("GOOGLE_SERVICE_ACCOUNT_JSON", None)
    variables["DJANGO_SETTINGS_MODULE"] = "finance_dashboard.settings_lambda"
    variables["DJANGO_SECRET_KEY"] = _required(environment, "DJANGO_SECRET_KEY")
    variables["ALLOWED_HOSTS"] = _required(environment, "ALLOWED_HOSTS")
    variables.pop("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", None)
    variables["CLOUDFLARE_ACCESS_ENABLED"] = access_mode

    access_names = (
        "CLOUDFLARE_ACCESS_TEAM_DOMAIN",
        "CLOUDFLARE_ACCESS_AUDIENCE",
        "CLOUDFLARE_ACCESS_ALLOWED_EMAIL",
    )
    if access_mode == "true":
        for name in access_names:
            variables[name] = _required(environment, name)
    else:
        for name in access_names:
            variables.pop(name, None)

    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="zappa_settings.json")
    args = parser.parse_args()
    path = Path(args.config)
    config = json.loads(path.read_text(encoding="utf-8"))
    patched = patch_settings(config, os.environ)
    path.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()