from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "refresh.yml"
WAKE_WORKFLOW = ROOT / ".github" / "workflows" / "refresh-wake.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "site.yml"
EXPECTED_CRON = "7,17,27,37,47,57 * * * *"
EXPECTED_WAKE_DISPATCH = "gh workflow run refresh.yml --repo myplexscripts/news --ref main"
EXPECTED_SITE_DISPATCH = "gh workflow run site.yml --repo myplexscripts/news --ref main"


def main() -> int:
    errors: list[str] = []

    if not REFRESH_WORKFLOW.exists():
        errors.append("refresh.yml is missing")
        refresh = ""
    else:
        refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    if not WAKE_WORKFLOW.exists():
        errors.append("refresh-wake.yml is missing")
        wake = ""
    else:
        wake = WAKE_WORKFLOW.read_text(encoding="utf-8")

    if not DEPLOY_WORKFLOW.exists():
        errors.append("site.yml is missing")
        deploy = ""
    else:
        deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    cron_values = re.findall(r"-\s*cron:\s*['\"]([^'\"]+)['\"]", refresh)
    if EXPECTED_CRON not in cron_values:
        errors.append(f"expected resilient refresh cron {EXPECTED_CRON!r}, found {cron_values or 'none'}")

    if re.search(r"^\s+timezone\s*:", refresh, flags=re.MULTILINE):
        errors.append("unsupported 'timezone:' key found in refresh schedule")

    if "workflow_dispatch:" not in refresh:
        errors.append("refresh workflow is missing manual workflow_dispatch fallback")

    if "paths:" not in refresh or "'scripts/**'" not in refresh:
        errors.append("collector changes should trigger a refresh without making data commits recursive")

    if "id: due" not in refresh or "Decide whether refresh is due" not in refresh:
        errors.append("refresh workflow is missing the freshness gate")

    if "age_minutes >= 20" not in refresh:
        errors.append("freshness gate must prevent unnecessary scheduled retries when the feed is under 20 minutes old")

    if "steps.due.outputs.run == 'true'" not in refresh:
        errors.append("expensive refresh steps are not guarded by the freshness decision")

    if "python scripts/run_scoop.py" not in refresh:
        errors.append("refresh workflow is bypassing the hardened Scoop runtime")

    if "python scripts/run_audit.py" not in refresh:
        errors.append("refresh workflow is bypassing the cluster-aware audit runner")

    if "python scripts/test_scoop_runtime.py" not in refresh:
        errors.append("Scoop runtime safeguard tests are missing from refresh workflow")

    if 'git commit -m "Refresh news"' not in refresh:
        errors.append("refresh workflow does not commit updated data with the current feed name")

    if "group: refresh-news-v3" not in refresh or "cancel-in-progress: false" not in refresh:
        errors.append("refresh workflow must queue overlapping runs instead of cancelling valid commits")

    if EXPECTED_SITE_DISPATCH not in refresh:
        errors.append("refresh workflow must explicitly deploy bot-authored data commits because GITHUB_TOKEN pushes do not trigger site.yml")

    if "steps.commit.outputs.changed == 'true'" not in refresh:
        errors.append("Pages deployment should only be dispatched when refreshed data was committed")

    if "Schedule next refresh" not in refresh:
        errors.append("refresh workflow is not scheduling its next wake-up")

    if "CYCLE_START_EPOCH=$(date +%s)" not in refresh:
        errors.append("refresh workflow is not recording the cycle start time")

    if "wait_seconds=$((900 - elapsed))" not in refresh:
        errors.append("refresh loop should target a 15-minute start-to-start cadence")

    if "gh workflow run refresh-wake.yml" not in refresh:
        errors.append("refresh workflow does not dispatch the separate wake-up workflow")

    if "if: always()" not in refresh:
        errors.append("refresh scheduling must survive scraper or audit failures")

    if "sleep \"$wait_seconds\"" in refresh or "sleep 900" in refresh:
        errors.append("refresh workflow must not remain open just to wait for its next cycle")

    if "workflow_dispatch:" not in wake:
        errors.append("wake workflow must support workflow_dispatch")

    if "delay_seconds:" not in wake:
        errors.append("wake workflow is missing its delay input")

    if "sleep \"$delay\"" not in wake:
        errors.append("wake workflow does not wait for the requested refresh window")

    if EXPECTED_WAKE_DISPATCH not in wake:
        errors.append("wake workflow does not explicitly dispatch the next refresh in myplexscripts/news")

    if "group: refresh-wake" not in wake or "cancel-in-progress: true" not in wake:
        errors.append("wake workflow must collapse duplicate timers into one active timer")

    if "schedule:" in deploy:
        errors.append("site.yml must remain deploy-only and must not have a schedule trigger")

    if "python scripts/run_scoop.py" in deploy or "python scripts/fetch_news.py" in deploy:
        errors.append("site.yml must not mutate news data during deployment")

    if "group: pages" not in deploy or "cancel-in-progress: false" not in deploy:
        errors.append("site deploys must queue instead of cancelling an in-progress commit deployment")

    lock_exists = (ROOT / "package-lock.json").exists() or (ROOT / "npm-shrinkwrap.json").exists()
    if lock_exists and "npm ci" not in deploy:
        errors.append("site.yml should use npm ci when a lockfile exists")
    if not lock_exists and "npm install" not in deploy:
        errors.append("site.yml needs npm install until the repository has a lockfile")

    if errors:
        print("Workflow configuration check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Workflow configuration OK: queued deploys, queued refreshes, explicit deploy after changed data commits, "
        "separate wake timer, approximately 15-minute start-to-start refresh loop, "
        f"cron backup ({EXPECTED_CRON}), and 20-minute scheduled freshness gate"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
