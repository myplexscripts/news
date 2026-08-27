from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "refresh.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "site.yml"
EXPECTED_CRON = "11,41 * * * *"


def main() -> int:
    errors: list[str] = []

    if not REFRESH_WORKFLOW.exists():
        errors.append("refresh.yml is missing")
        refresh = ""
    else:
        refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    if not DEPLOY_WORKFLOW.exists():
        errors.append("site.yml is missing")
        deploy = ""
    else:
        deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    cron_values = re.findall(r"-\s*cron:\s*['\"]([^'\"]+)['\"]", refresh)
    if EXPECTED_CRON not in cron_values:
        errors.append(f"expected refresh cron {EXPECTED_CRON!r}, found {cron_values or 'none'}")

    if re.search(r"^\s+timezone\s*:", refresh, flags=re.MULTILINE):
        errors.append("unsupported 'timezone:' key found in refresh schedule")

    if "workflow_dispatch:" not in refresh:
        errors.append("refresh workflow is missing manual workflow_dispatch fallback")

    if "python scripts/run_scoop.py" not in refresh:
        errors.append("refresh workflow is bypassing the hardened Scoop runtime")

    if "python scripts/run_audit.py" not in refresh:
        errors.append("refresh workflow is bypassing the cluster-aware audit runner")

    if "python scripts/test_scoop_runtime.py" not in refresh:
        errors.append("Scoop runtime safeguard tests are missing from refresh workflow")

    if 'git commit -m "Refresh local news"' not in refresh:
        errors.append("refresh workflow does not commit updated data")

    if "schedule:" in deploy:
        errors.append("site.yml must remain deploy-only and must not have a schedule trigger")

    if "python scripts/run_scoop.py" in deploy or "python scripts/fetch_news.py" in deploy:
        errors.append("site.yml must not mutate news data during deployment")

    if "npm ci" not in deploy:
        errors.append("site.yml should use deterministic npm ci installs")

    if errors:
        print("Workflow configuration check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Workflow configuration OK: dedicated refresh at :11 and :41 ({EXPECTED_CRON})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
