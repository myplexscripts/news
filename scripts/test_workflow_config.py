from pathlib import Path
import re
import sys

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "site.yml"
EXPECTED_CRON = "17,47 * * * *"


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    errors: list[str] = []

    if "schedule:" not in text:
        errors.append("site.yml is missing the schedule trigger")

    cron_values = re.findall(r"-\s*cron:\s*['\"]([^'\"]+)['\"]", text)
    if EXPECTED_CRON not in cron_values:
        errors.append(
            f"expected refresh cron {EXPECTED_CRON!r}, found {cron_values or 'none'}"
        )

    # GitHub Actions schedule entries support cron only. A timezone key looks
    # plausible but prevents the schedule from being registered correctly.
    if re.search(r"^\s+timezone\s*:", text, flags=re.MULTILINE):
        errors.append("unsupported 'timezone:' key found under GitHub Actions schedule")

    if "workflow_dispatch:" not in text:
        errors.append("manual workflow_dispatch fallback is missing")

    if "python scripts/run_scoop.py" not in text:
        errors.append("workflow is bypassing the hardened Scoop runtime runner")

    if "python scripts/test_scoop_runtime.py" not in text:
        errors.append("Scoop runtime safeguard tests are missing from the workflow")

    # Scheduled runs commit refreshed JSON/cache back to main. That bot commit
    # must not spawn another push-triggered copy of the same expensive workflow.
    if 'git commit -m "Refresh local news [skip ci]"' not in text:
        errors.append("refresh bot commit must contain [skip ci] to prevent duplicate runs")

    if errors:
        print("Workflow configuration check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Workflow configuration OK: refreshes at :17 and :47 ({EXPECTED_CRON})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
