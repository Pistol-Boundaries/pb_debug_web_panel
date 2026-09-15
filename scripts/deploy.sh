#!/usr/bin/env bash
set -euo pipefail

# Resolve the repository even when invoked from another working directory.
PANEL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PANEL_ROOT"

for cli in gcloud firebase; do
  if ! command -v "$cli" >/dev/null 2>&1; then
    echo "Missing $cli. See FIREBASE_DEPLOY.md for setup." >&2
    exit 1
  fi
done

PANEL_PROJECT="pistol-boundaries-sb"
PANEL_SERVICE="activity-log-viewer"
PANEL_REGION="us-central1"

# Require the existing service: initial provisioning is documented separately.
gcloud run services describe "$PANEL_SERVICE" \
  --project "$PANEL_PROJECT" --region "$PANEL_REGION" \
  --format='value(metadata.name)' >/dev/null

echo "Deploying the debug panel to $PANEL_PROJECT..."
# Omit environment, secret, IAM, and scaling flags to preserve live settings.
gcloud run deploy "$PANEL_SERVICE" \
  --source . \
  --project "$PANEL_PROJECT" \
  --region "$PANEL_REGION"

firebase deploy --only hosting:debug-panel --project "$PANEL_PROJECT" --non-interactive

echo "Deployed: https://pb-debug-panel.web.app"
