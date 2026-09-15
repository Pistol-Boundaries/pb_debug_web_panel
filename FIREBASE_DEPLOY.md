# Deploy the debug panel to Firebase

This repository deploys only the `debug-panel` Hosting target and its dedicated
Cloud Run service `activity-log-viewer`. Keep the existing website on its own site.
The database stays in Supabase. Region: `us-central1` (change both commands and
firebase.json together if a different supported region is needed).

## Deploy updates

From the project folder, run:

```sh
./scripts/deploy.sh
```

The script builds and deploys the current local source to the existing Cloud Run
service, then deploys only the `debug-panel` Firebase Hosting target. It preserves
the service's configured environment variables, secret bindings, service account,
IAM policy, and scaling settings. No local `.env` file is needed. If a command
fails, the script stops; if Hosting fails after Cloud Run succeeds, the backend
has already been updated. Fix the reported problem and rerun the script.

Each developer needs `gcloud` and `firebase` installed, then must sign in with
`gcloud auth login` and `firebase login` using accounts authorized for
`pistol-boundaries-sb`. An administrator must grant the deployment permissions,
including source-build/deploy access, permission to act as the runtime service
account, and Firebase Hosting deployment access. Runtime secret access alone
is not developer deployment access.

After deployment, check login, logs, map filtering, and logout at
https://pb-debug-panel.web.app.

## Initial provisioning (already completed)

Teammates deploying updates should use the script above, not repeat this setup.


Install Google Cloud CLI (`gcloud`) and Firebase CLI (`firebase`). Then authenticate:

```sh
gcloud auth login
firebase login
```

Set these values to the actual project ID and a NEW globally unique Hosting site ID:

```sh
export PANEL_PROJECT_ID='pistol-boundaries-sb'
export PANEL_SITE_ID='pb-debug-panel'
firebase hosting:sites:list --project "$PANEL_PROJECT_ID"
firebase hosting:sites:create "$PANEL_SITE_ID" --project "$PANEL_PROJECT_ID"
firebase target:apply hosting debug-panel "$PANEL_SITE_ID" --project "$PANEL_PROJECT_ID"
```

The last command adds the site target to `.firebaserc`; commit it so teammates use the same target.
Do not assign the existing application's site to `debug-panel`.

Enable Cloud Run, Cloud Build, Artifact Registry, and Secret Manager APIs in the
Google Cloud project. Create a dedicated runtime service account and give it
Secret Manager Secret Accessor on the panel's secrets only.

In Secret Manager create these secrets using the existing application values:

- `panel-supabase-key`
- `panel-app-password` (use a non-default password)
- `panel-session-secret` (use a strong, stable random value)

Do not put secret values in source files or shell history. The runtime service
account email below is the account you created in the project.

## Initial Cloud Run deployment

```sh
export PANEL_SUPABASE_URL='YOUR_SUPABASE_URL'
export PANEL_RUNTIME_ACCOUNT='YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL'
gcloud run deploy activity-log-viewer --source . --project "$PANEL_PROJECT_ID" --region us-central1 --allow-unauthenticated --service-account "$PANEL_RUNTIME_ACCOUNT" --min-instances 0 --max-instances 3 --set-env-vars "SUPABASE_URL=$PANEL_SUPABASE_URL,SUPABASE_LOGS_TABLE=activity_logs,DEFAULT_LOG_LIMIT=100,SESSION_HTTPS_ONLY=true" --set-secrets 'SUPABASE_KEY=panel-supabase-key:latest,APP_PASSWORD=panel-app-password:latest,SESSION_SECRET=panel-session-secret:latest'
firebase deploy --only hosting:debug-panel --project "$PANEL_PROJECT_ID"
```

Public Cloud Run invocation allows Hosting to reach the server; the application
still requires its password. The image and source upload include only application
files and dependencies, excluding `.env`, local credentials, and tests.

Open the Hosting URL printed by Firebase. Verify login persists, logs load,
map filtering works, and logout blocks access. Keep Render until those checks pass.
The `__session` cookie name is required for Firebase Hosting cookie forwarding;
existing users will need to log in again. Dynamic responses are not cached.

## Local container check

```sh
docker build -t activity-log-viewer .
docker run --rm -p 8080:8080 --env-file .env activity-log-viewer
```

Use http://localhost:8080. Keep SESSION_HTTPS_ONLY=false locally (the default).

References: [Cloud Run integration](https://firebase.google.com/docs/hosting/cloud-run),
[multiple sites](https://firebase.google.com/docs/hosting/multisites),
[cookie forwarding](https://firebase.google.com/docs/hosting/manage-cache#using_cookies).

## GitHub Actions

Pull requests run checks; successful pushes to main deploy automatically once
Google/GitHub authentication is configured. See [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md)
for the one-time setup.
