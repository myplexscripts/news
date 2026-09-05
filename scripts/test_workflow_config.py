from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "refresh.yml"
WAKE_WORKFLOW = ROOT / ".github" / "workflows" / "refresh-wake.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "site.yml"

EXPECTED_CRON = "7,17,27,37,47,57 * * * *"
EXPECTED_WAKE_DISPATCH = 'gh workflow run refresh-wake.yml --repo "$GITHUB_REPOSITORY" --ref main -f delay_seconds="$wait_seconds"'
EXPECTED_REFRESH_DISPATCH = "gh workflow run refresh.yml --repo myplexscripts/news --ref main"
EXPECTED_SITE_DISPATCH = "gh workflow run site.yml --repo myplexscripts/news --ref main"
WATCHDOG_WAKE_GUARD = "github.event_name != 'schedule' || steps.due.outputs.run == 'true'"


def main() -> int:
    errors: list[str] = []

    refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8") if REFRESH_WORKFLOW.exists() else ""
    wake = WAKE_WORKFLOW.read_text(encoding="utf-8") if WAKE_WORKFLOW.exists() else ""
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8") if DEPLOY_WORKFLOW.exists() else ""

    if not refresh:
        errors.append("refresh.yml is missing")
    if not wake:
        errors.append("refresh-wake.yml is missing")
    if not deploy:
        errors.append("site.yml is missing")

    cron_values = re.findall(r"-\s*cron:\s*['\"]([^'\"]+)['\"]", refresh)
    if EXPECTED_CRON not in cron_values:
        errors.append(f"expected watchdog cron {EXPECTED_CRON!r}, found {cron_values or 'none'}")

    if "workflow_dispatch:" not in refresh:
        errors.append("refresh workflow is missing manual workflow_dispatch fallback")

    if "'scripts/**'" not in refresh or "'.github/workflows/refresh-wake.yml'" not in refresh:
        errors.append("refresh workflow push triggers do not cover scheduler and collector changes")

    if "id: due" not in refresh or "Decide whether refresh is due" not in refresh:
        errors.append("refresh workflow is missing the freshness gate")

    if "age_minutes >= 20" not in refresh:
        errors.append("scheduled watchdog runs must refresh feeds at least 20 minutes old")

    if "python scripts/run_fast_scoop.py" not in refresh:
        errors.append("refresh workflow is bypassing the bounded fast collector")

    if "python scripts/run_audit.py" not in refresh:
        errors.append("refresh workflow is bypassing the audit runner")

    if "python scripts/test_workflow_config.py" not in refresh:
        errors.append("refresh workflow is not validating its scheduler configuration")

    if 'git commit -m "Refresh news"' not in refresh:
        errors.append("refresh workflow does not commit updated feed data")

    if "group: refresh-news-v5" not in refresh or "cancel-in-progress: false" not in refresh:
        errors.append("refresh workflow must queue overlapping triggers instead of cancelling active work")

    if EXPECTED_SITE_DISPATCH not in refresh:
        errors.append("refresh workflow must explicitly deploy bot-authored feed commits")

    if "Start deferred article enrichment" not in refresh or "gh workflow run enrich.yml" not in refresh:
        errors.append("refresh workflow must hand new stories to deferred article enrichment")

    if "Record refresh cycle start" not in refresh or "CYCLE_START_EPOCH=$(date +%s)" not in refresh:
        errors.append("refresh workflow is not recording its cycle start time")

    if "Schedule next refresh" not in refresh or EXPECTED_WAKE_DISPATCH not in refresh:
        errors.append("refresh workflow is not chaining its next wake-up")

    if "wait_seconds=$((900 - elapsed))" not in refresh:
        errors.append("refresh loop should target an approximately 15-minute start-to-start cadence")

    if WATCHDOG_WAKE_GUARD not in refresh:
        errors.append("fresh watchdog checks must not reset the active wake timer")

    if "sleep \"$wait_seconds\"" in refresh or "sleep 900" in refresh:
        errors.append("refresh workflow must not stay open only to wait for the next cycle")

    if "workflow_dispatch:" not in wake or "delay_seconds:" not in wake:
        errors.append("wake workflow is missing dispatch support or its delay input")

    if 'sleep "$delay"' not in wake or EXPECTED_REFRESH_DISPATCH not in wake:
        errors.append("wake workflow does not wait and dispatch the next refresh")

    if "group: refresh-wake" not in wake or "cancel-in-progress: true" not in wake:
        errors.append("wake workflow must collapse duplicate timers into one active timer")

    if "schedule:" in deploy:
        errors.append("site.yml must remain deploy-only")

    if "cp data/news.json public/data/news.json" not in deploy:
        errors.append("site.yml must publish data/news.json into the Pages artifact")

    if "cp data/audit.json public/data/audit.json" not in deploy:
        errors.append("site.yml must publish data/audit.json into the Pages artifact")

    if errors:
        print("Workflow configuration check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Workflow configuration OK: chained 15-minute refresh wake, 10-minute watchdog, "
        "20-minute freshness fallback, queued refreshes, fast collection, enrichment, and explicit deployment"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
