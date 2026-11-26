# Deploying Ask the Multiverse to Google Cloud

Same pattern as Flowbench, doppel and mahakal, in its **own GCP project**:

- **Firebase Hosting** (site `ask-the-multiverse`, custom domain
  `multiverse.arunangshupramanik.com`) serves `frontend/dist`. The
  `/multiverse/api/**` rewrite comes before the SPA fallback and points to Cloud Run.
- **Cloud Run** service `multiverse-api` in `asia-south1` runs the FastAPI image from
  **Artifact Registry** repository `multiverse`. It scales to zero.
- **Cloud Storage** bucket `<PROJECT_ID>-multiverse-data` holds the DuckDB data snapshots
  (`serve/multiverse-<run>.duckdb`), the pointer `serve/latest.json` and build reports.
  The API downloads the snapshot at start-up and re-checks the pointer every 15 minutes.
- **GitHub Actions**, all keyless (**Workload Identity Federation**, no JSON keys):
  - `ci.yml`: backend tests (incl. golden fixtures, rule-planner evaluation and deployment
    consistency), Docker build, frontend tests, build and `npm audit`.
  - `deploy.yml`: runs only after a successful **push CI on main**, waits for **your approval**
    in the GitHub `production` environment, re-runs tests, deploys the API, checks it, deploys
    Hosting, then runs `scripts/smoke.py`.
  - `sync.yml`: weekly (and on demand) full refresh from the Marvel Database and MCU Wiki
    APIs. Publishes a new snapshot only if every quality check passes. No approval needed and
    no redeploy: it can only write to the data bucket.
- **Secret Manager** holds the optional Groq / Gemini keys. Without them the Console uses its
  rule-based planner.

## Runtime design and cost

| Setting | Value | Why |
| --- | --- | --- |
| CPU / memory | 1 vCPU / 1 GiB | the ~100 MB snapshot lives in `/tmp`, which counts against memory |
| Scaling | min 0, max 1, CPU only during requests, startup CPU boost | demo traffic; one instance keeps rate limits and the answer cache consistent and bounds LLM spend |
| Cold start | about 5-10 s | image start + snapshot download from GCS in the same region |
| Concurrency / timeout | 20 / 60 s | answers take well under a second without an LLM, a few seconds with one |
| Rate limits | 6 questions/min per visitor (`__session` cookie, best effort), 30/min site-wide | keeps LLM usage inside free tiers |
| Data refresh | weekly full rebuild, about 7,000 API calls at 1/s | polite to Fandom; nightly would repeat ~7,000 calls every day |

Expected cost at demo traffic: about **USD 1-3/month** (Cloud Run inside the free tier,
GCS ~0.5 GB, Artifact Registry images, Secret Manager). GitHub Actions minutes are free because
the repository is public. Check the
[Cloud Run pricing calculator](https://cloud.google.com/products/calculator) before deploying;
prices and free tiers change. Hosting streams are buffered: the Console still works, but steps
arrive together with the answer rather than one by one.

## Manual setup, in order

Do one step at a time and confirm it before continuing. Console steps (billing, Firebase,
DNS) are manual. Commands are references, **not an idempotent script**: stop on errors and
check existing resources before retrying. Never paste tokens or keys into chat.

### 1. Create a separate project, link billing, set a budget

In Google Cloud Console:

1. Create a project named **ask-the-multiverse** with a unique project ID, for example
   `ask-the-multiverse-<ddmmyy>`. Do **not** reuse the portfolio (`ap-portfolio-241026`),
   mahakal (`mahakal-ai-230925`), doppel (`doppel-101126`) or Flowbench projects; the
   workflows refuse them.
2. Link the intended billing account.
3. In **Billing > Budgets & alerts**, create a budget scoped **only to this project**, for
   example INR 500/month with alerts at 50%, 90% and 100%. Budgets notify; they do not cap
   spending.

### 2. Add Firebase and create the Hosting site

In Firebase Console choose **Add Firebase to an existing Google Cloud project** and pick the
new project (Analytics not needed). In **Hosting**, create the site **`ask-the-multiverse`**.
If that ID is taken, pick another and tell me, so `firebase.json`,
`backend/tests/test_deployment.py` and the docs can be updated. Do not run `firebase init`
over the checked-in config.

### 3. Authenticate the terminal and set identifiers

From the repository root:

```bash
gcloud auth login           # if not already logged in
gh auth status              # logged in as arunangshu01
export PROJECT_ID='YOUR_NEW_PROJECT_ID'
export REGION='asia-south1'
export GITHUB_REPO='arunangshu01/ask-the-multiverse'
export BUCKET="${PROJECT_ID}-multiverse-data"
export RUN_SA="multiverse-run@${PROJECT_ID}.iam.gserviceaccount.com"
export DEPLOY_SA="multiverse-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
export SYNC_SA="multiverse-sync@${PROJECT_ID}.iam.gserviceaccount.com"
case "$PROJECT_ID" in
  ''|YOUR_*|ap-portfolio-241026|mahakal-ai-230925|doppel-101126|flowbench-*) echo 'STOP: select the new project' ;;
  *) gcloud config set project "$PROJECT_ID" ;;
esac
gcloud projects describe "$PROJECT_ID" --format='table(projectId,name,projectNumber)'
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
export REPO_ID=$(gh api "repos/$GITHUB_REPO" --jq '.id')         # 1465783924
export OWNER_ID=$(gh api "repos/$GITHUB_REPO" --jq '.owner.id')  # 22813216
```

Keep this terminal open so the exports survive.

### 4. Enable APIs, create the image registry and the data bucket

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com \
  firebase.googleapis.com firebasehosting.googleapis.com \
  cloudresourcemanager.googleapis.com serviceusage.googleapis.com \
  --project="$PROJECT_ID"

gcloud artifacts repositories create multiverse --project="$PROJECT_ID" \
  --repository-format=docker --location="$REGION" --description='Ask the Multiverse API images'

gcloud storage buckets create "gs://$BUCKET" --project="$PROJECT_ID" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention
```

### 5. Service accounts and IAM

```bash
gcloud iam service-accounts create multiverse-run --project="$PROJECT_ID" \
  --display-name='Ask the Multiverse Cloud Run runtime'
gcloud iam service-accounts create multiverse-deployer --project="$PROJECT_ID" \
  --display-name='Ask the Multiverse GitHub deployer'
gcloud iam service-accounts create multiverse-sync --project="$PROJECT_ID" \
  --display-name='Ask the Multiverse GitHub data sync'

# deployer: deploy Cloud Run and Hosting, push images, act as the runtime account
for role in roles/run.admin roles/firebasehosting.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$DEPLOY_SA" --role="$role"
done
gcloud artifacts repositories add-iam-policy-binding multiverse --project="$PROJECT_ID" \
  --location="$REGION" --member="serviceAccount:$DEPLOY_SA" --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" --project="$PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role=roles/iam.serviceAccountUser

# data bucket: the runtime and the deployer read, only the sync job writes
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$RUN_SA" --role=roles/storage.objectViewer
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$DEPLOY_SA" --role=roles/storage.objectViewer
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SYNC_SA" --role=roles/storage.objectAdmin
```

No account gets Owner or Editor. The sync account can touch only the data bucket.

### 6. LLM keys in Secret Manager (optional)

Skip this step to launch with the rule-based planner; you can add keys later.
Run these yourself; each command reads the key from a hidden prompt, so it never appears in
shell history or chat:

```bash
read -rs GROQ_KEY && printf '%s' "$GROQ_KEY" | gcloud secrets create multiverse-groq-api-key \
  --project="$PROJECT_ID" --replication-policy=automatic --data-file=- && unset GROQ_KEY
read -rs GEMINI_KEY && printf '%s' "$GEMINI_KEY" | gcloud secrets create multiverse-gemini-api-key \
  --project="$PROJECT_ID" --replication-policy=automatic --data-file=- && unset GEMINI_KEY

for s in multiverse-groq-api-key multiverse-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$s" --project="$PROJECT_ID" \
    --member="serviceAccount:$RUN_SA" --role=roles/secretmanager.secretAccessor
done
```

If you only create one of the two, list only that one in Step 8.

### 7. Keyless Workload Identity Federation (two providers)

The repository uses immutable OIDC subjects (`use_immutable_subject: true`):

```bash
export OIDC_SUB_PREFIX=$(gh api "repos/$GITHUB_REPO/actions/oidc/customization/sub" --jq '.sub_claim_prefix // empty')
echo "$OIDC_SUB_PREFIX"   # expected: repo:arunangshu01@22813216/ask-the-multiverse@1465783924
```

If it is empty or different, stop and check before continuing.

One pool per workflow, so each service account trusts only tokens that passed its own
workflow's condition:

```bash
MAP='google.subject=assertion.sub,attribute.repository_id=assertion.repository_id'

# deploy: only deploy.yml on main, in the approved production environment
gcloud iam workload-identity-pools create github-deploy --project="$PROJECT_ID" \
  --location=global --display-name='Multiverse deploy workflow'
gcloud iam workload-identity-pools providers create-oidc multiverse-deploy \
  --project="$PROJECT_ID" --location=global --workload-identity-pool=github-deploy \
  --display-name='Production deploy workflow' \
  --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping="$MAP" \
  --attribute-condition="assertion.repository_id=='${REPO_ID}' && assertion.repository_owner_id=='${OWNER_ID}' && assertion.ref=='refs/heads/main' && assertion.workflow_ref=='${GITHUB_REPO}/.github/workflows/deploy.yml@refs/heads/main' && assertion.sub=='${OIDC_SUB_PREFIX:?Check the OIDC subject prefix first}:environment:production'"

# sync: only sync.yml on main (scheduled, no environment)
gcloud iam workload-identity-pools create github-sync --project="$PROJECT_ID" \
  --location=global --display-name='Multiverse data sync workflow'
gcloud iam workload-identity-pools providers create-oidc multiverse-sync \
  --project="$PROJECT_ID" --location=global --workload-identity-pool=github-sync \
  --display-name='Data sync workflow' \
  --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping="$MAP" \
  --attribute-condition="assertion.repository_id=='${REPO_ID}' && assertion.repository_owner_id=='${OWNER_ID}' && assertion.ref=='refs/heads/main' && assertion.workflow_ref=='${GITHUB_REPO}/.github/workflows/sync.yml@refs/heads/main' && assertion.sub=='${OIDC_SUB_PREFIX:?Check the OIDC subject prefix first}:ref:refs/heads/main'"

POOLS="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --project="$PROJECT_ID" \
  --role=roles/iam.workloadIdentityUser --member="${POOLS}/github-deploy/attribute.repository_id/${REPO_ID}"
gcloud iam service-accounts add-iam-policy-binding "$SYNC_SA" --project="$PROJECT_ID" \
  --role=roles/iam.workloadIdentityUser --member="${POOLS}/github-sync/attribute.repository_id/${REPO_ID}"

export WIF_DEPLOY="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-deploy/providers/multiverse-deploy"
export WIF_SYNC="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-sync/providers/multiverse-sync"
printf 'GCP_WIF_PROVIDER=%s\nGCP_SYNC_WIF_PROVIDER=%s\n' "$WIF_DEPLOY" "$WIF_SYNC"
```

Each service account can be impersonated only by its own workflow file. Allow a few minutes
for IAM propagation before diagnosing auth failures; do not loosen the conditions as a
workaround.

### 8. GitHub Actions Variables (not Secrets)

```bash
gh variable set GCP_PROJECT_ID --repo "$GITHUB_REPO" --body "$PROJECT_ID"
gh variable set GCP_DEPLOY_SA --repo "$GITHUB_REPO" --body "$DEPLOY_SA"
gh variable set GCP_WIF_PROVIDER --repo "$GITHUB_REPO" --body "$WIF_DEPLOY"
gh variable set GCP_SYNC_SA --repo "$GITHUB_REPO" --body "$SYNC_SA"
gh variable set GCP_SYNC_WIF_PROVIDER --repo "$GITHUB_REPO" --body "$WIF_SYNC"
# only if you did Step 6 (names of the secrets, not their values):
gh variable set MULTIVERSE_LLM_SECRETS --repo "$GITHUB_REPO" \
  --body 'GROQ_API_KEY=multiverse-groq-api-key:latest,GEMINI_API_KEY=multiverse-gemini-api-key:latest'
```

These are identifiers, not secrets.

### 9. Protect production and main

In **Settings > Environments**, create **production**:

- Deployment branches: selected branches, **main** only.
- **Required reviewers**: `arunangshu01` (leave *Prevent self-review* unchecked).
- Disable *Allow administrators to bypass configured protection rules*.

In **Settings > Rules > Rulesets**, create `Protect main` like Flowbench's: target `main`,
require a pull request (0 approvals), require conversation resolution and up-to-date
branches, require the status checks **Backend tests** and **Frontend tests and build**, block
force pushes and deletion. Enable secret scanning and push protection.

### 10. First data sync

The API needs a snapshot before its first deploy:

1. Push the code to `main` (or merge the PR).
2. **Actions > Sync > Run workflow** on `main`. It takes about 2-3 hours.
3. When it is green, check: `gcloud storage ls "gs://$BUCKET/serve/"` shows
   `latest.json` and one `multiverse-g<date>.duckdb`.

If a quality check fails, nothing is published; the run uploads its `report.json` files as an
artifact. Send me the failing check line (not credentials).

### 11. Approve the first deploy

1. After a successful push CI on `main`, **Deploy** waits for approval. Open
   **Actions > Deploy > Review deployments**, select **production**, **Approve and deploy**.
   Only you approve.
2. If Deploy ran before the first sync finished, it stops at "Check a data snapshot is
   published". Re-run that CI run after the sync is green.
3. Verify:

```bash
python3 scripts/smoke.py https://ask-the-multiverse.web.app
```

### 12. Custom domain

1. Firebase Console > Hosting > **Add custom domain** > `multiverse.arunangshupramanik.com`.
2. Add the DNS records Firebase shows at the DNS provider for `arunangshupramanik.com` (the
   same place as the other subdomains). Do not change the existing records for the apex or
   other subdomains.
3. Wait for Firebase to show **Connected** (certificate issuance can take up to a day), then
   run `python3 scripts/smoke.py https://multiverse.arunangshupramanik.com`.

## Operations and rollback

- Logs: Cloud Run > multiverse-api > Logs. Sync history: Actions > Sync.
- New data goes live within 15 minutes of a green sync (or at the next cold start).
- Bad data: the sync keeps the 4 newest snapshots in `gs://$BUCKET/serve/`. To roll back,
  download `serve/latest.json`, change `db` and `run_id` to the previous snapshot, and upload it
  again. The API switches within 15 minutes.
- Code rollback: revert via PR, pass CI, merge, approve Deploy. Emergency: restore a
  known-good Cloud Run revision and Hosting release in their consoles.
- Optional: an uptime check on `https://multiverse.arunangshupramanik.com/multiverse/api/v1/health`
  with an email alert, like Flowbench.
