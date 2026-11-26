"""Keep the deployment files consistent with the app (prefix, names, guards)."""

import json
import pathlib
import re

from app.settings import API_COMMON_PREFIX

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / ".github/workflows/deploy.yml").read_text()
SYNC = (ROOT / ".github/workflows/sync.yml").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()
FIREBASE = json.loads((ROOT / "firebase.json").read_text())["hosting"]
ENV = dict(line.split(": ", 1) for line in (ROOT / "deploy/cloud-run.env.yaml").read_text().splitlines() if line.strip())
CLIENT = (ROOT / "frontend/src/api/client.js").read_text()
VITE = (ROOT / "frontend/vite.config.js").read_text()
DOCKERFILE = (ROOT / "backend/Dockerfile").read_text()


def test_prefix_is_consistent_everywhere():
    base = API_COMMON_PREFIX.rsplit("/", 1)[0]  # /multiverse/api
    assert f'API_PREFIX = "{API_COMMON_PREFIX}"' in CLIENT
    assert f'"{base}"' in VITE
    assert f"API_PREFIX: {API_COMMON_PREFIX}" in DEPLOY
    api_rewrite = FIREBASE["rewrites"][0]
    assert api_rewrite["source"] == f"{base}/**"
    assert api_rewrite["run"] == {"serviceId": "multiverse-api", "region": "asia-south1"}
    assert FIREBASE["rewrites"][-1] == {"source": "**", "destination": "/index.html"}  # SPA fallback last


def test_hosting_service_and_account_names():
    assert FIREBASE["site"] == "ask-the-multiverse" and re.fullmatch(r"[a-z0-9][a-z0-9-]+", FIREBASE["site"])
    assert "url: https://multiverse.arunangshupramanik.com" in DEPLOY
    assert "SERVICE: multiverse-api" in DEPLOY and "REGION: asia-south1" in DEPLOY
    assert "multiverse-run@${PROJECT_ID}.iam.gserviceaccount.com" in DEPLOY
    assert '"multiverse-deployer@${PROJECT_ID}.iam.gserviceaccount.com"' in DEPLOY
    assert '"multiverse-sync@${PROJECT_ID}.iam.gserviceaccount.com"' in SYNC
    assert "docker.pkg.dev/${PROJECT_ID}/multiverse/api:${COMMIT}" in DEPLOY
    # the API and the sync job agree on the bucket and prefix
    assert "${PROJECT_ID}-multiverse-data" in DEPLOY and "${PROJECT_ID}-multiverse-data" in SYNC
    assert ENV["MULTIVERSE_SNAPSHOT_PREFIX"] == '"serve"' and "$BUCKET/serve/latest.json" in SYNC


def test_deploy_and_sync_are_keyless_and_isolated():
    for wf in (DEPLOY, SYNC):
        for guard in ("ap-portfolio-241026", "mahakal-ai-230925", "doppel-101126", "flowbench-*"):
            assert guard in wf
        assert "credentials_json" not in wf and "secrets." not in wf
        assert wf.count("id-token: write") == 1
    assert "workflows: [CI]" in DEPLOY and "github.event.workflow_run.conclusion == 'success'" in DEPLOY
    assert "name: production" in DEPLOY and "workflow_dispatch" not in DEPLOY
    assert "workload_identity_provider: ${{ vars.GCP_WIF_PROVIDER }}" in DEPLOY
    assert "workload_identity_provider: ${{ vars.GCP_SYNC_WIF_PROVIDER }}" in SYNC


def test_cloud_run_matches_runtime_design():
    for flag in ("--min-instances 0", "--max-instances 1", "--cpu-throttling", "--memory 1Gi"):
        assert flag in DEPLOY
    assert "MULTIVERSE_DATA_DIR=/tmp/multiverse" in DOCKERFILE and ENV["MULTIVERSE_DATA_DIR"] == '"/tmp/multiverse"'
    assert "requirements.txt" in DOCKERFILE and "requirements-dev" not in DOCKERFILE


def test_sync_publishes_pointer_last_and_only_after_checks():
    publish = SYNC.split("name: Publish", 1)[1].split("- name:", 1)[0]
    assert publish.index("\"$BUCKET/serve/$DB\"") < publish.index("\"$BUCKET/serve/latest.json\"")
    assert "data/serve/published.json" in SYNC  # row-count checks compare with the live snapshot


def test_ci_job_names_match_required_checks():
    assert "name: Backend tests" in CI and "name: Frontend tests and build" in CI
