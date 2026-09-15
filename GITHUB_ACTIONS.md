# Automatic checks and deployment

`.github/workflows/deploy.yml` checks every pull request and push to main.
Only successful pushes to main deploy the shared debug panel, using
`scripts/deploy.sh`. Pull requests do not receive Google credentials or deploy.
Tests use dummy credentials and mocked database reads. Firebase integration tests
that create real users are deliberately excluded.

## One-time Google Cloud setup

An administrator runs these commands locally. These create a separate deployment
identity; the existing `pb-debug-panel` account remains the runtime identity.

```sh
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project pistol-boundaries-sb
gcloud iam service-accounts create pb-debug-deployer --display-name='PB Debug GitHub deployer' --project pistol-boundaries-sb

for role in roles/run.sourceDeveloper roles/serviceusage.serviceUsageConsumer roles/firebasehosting.admin; do
  gcloud projects add-iam-policy-binding pistol-boundaries-sb --member='serviceAccount:pb-debug-deployer@pistol-boundaries-sb.iam.gserviceaccount.com' --role="$role"
done

gcloud iam service-accounts add-iam-policy-binding pb-debug-panel@pistol-boundaries-sb.iam.gserviceaccount.com --member='serviceAccount:pb-debug-deployer@pistol-boundaries-sb.iam.gserviceaccount.com' --role=roles/iam.serviceAccountUser --project pistol-boundaries-sb

gcloud iam workload-identity-pools create pb-debug-github --location=global --display-name='PB Debug GitHub' --project pistol-boundaries-sb

gcloud iam workload-identity-pools providers create-oidc github --workload-identity-pool=pb-debug-github --location=global --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping='google.subject=assertion.sub,attribute.repository=assertion.repository' --attribute-condition="assertion.repository == 'Pistol-Boundaries/pb_debug_web_panel' && assertion.ref == 'refs/heads/main' && assertion.event_name == 'push'" --project pistol-boundaries-sb

gcloud iam service-accounts add-iam-policy-binding pb-debug-deployer@pistol-boundaries-sb.iam.gserviceaccount.com --role=roles/iam.workloadIdentityUser --member='principalSet://iam.googleapis.com/projects/696381632531/locations/global/workloadIdentityPools/pb-debug-github/attribute.repository/Pistol-Boundaries/pb_debug_web_panel' --project pistol-boundaries-sb
```

The project's existing Cloud Build identity must retain its source-build
permissions (the manual deployment already used it). The deployer can act as the
runtime account, but does not need access to secret values. Firebase Hosting
Admin is project-wide, including the other site; the workflow targets only
`debug-panel`. Restrict who can change workflows and push or merge to main.

## GitHub configuration

In `Pistol-Boundaries/pb_debug_web_panel`, open Settings → Secrets and variables → Actions →
Variables. Create these repository variables (not secrets):

| Name | Value |
| --- | --- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/696381632531/locations/global/workloadIdentityPools/pb-debug-github/providers/github` |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `pb-debug-deployer@pistol-boundaries-sb.iam.gserviceaccount.com` |

No service account JSON key, `.env`, or application password is stored in GitHub.
Google's auth action creates short-lived credentials for the deployment job.
The source-upload allowlist excludes those generated credentials.

Commit the workflow and deployment files, then merge to main. Follow the run in
GitHub's Actions tab. Deployment is serialized and stops on failure; if Cloud Run
succeeds before Hosting fails, the backend is already updated. A new successful
push to main retries deployment. Developers can still run the local script.

References: [Google GitHub authentication](https://github.com/google-github-actions/auth),
[source deployment roles](https://cloud.google.com/run/docs/deploying-source-code),
[Firebase CLI credentials](https://firebase.google.com/docs/cli#cli-ci-systems).
