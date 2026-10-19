#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# UbuntuBio Hub - Google Cloud Run Deployment Script (Option A: Sidecar)
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo "")}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="ubuntubio-backend"
AR_REPO="ubuntubio"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-ubuntubio-data}"
IMAGE_SERVER="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/server:latest"

echo "=== UbuntuBio Cloud Run Deployment ==="
echo "Project ID: ${PROJECT_ID}"
echo "Region:     ${REGION}"
echo "Service:    ${SERVICE_NAME}"
echo "Storage:    gs://${BUCKET_NAME}"
echo "Image:      ${IMAGE_SERVER}"
echo "========================================"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: No active GCP project configured. Run 'gcloud config set project <PROJECT_ID>'." >&2
  exit 1
fi

# 1. Enable Required GCP APIs
echo "--> Enabling required APIs (run, artifactregistry, storage)..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  --project="${PROJECT_ID}"

# 2. Ensure Artifact Registry repository exists
echo "--> Verifying Artifact Registry repository..."
if ! gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Creating Artifact Registry repository '${AR_REPO}'..."
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="UbuntuBio container images" \
    --project="${PROJECT_ID}"
fi

# 3. Ensure Cloud Storage bucket for persistent volume exists
echo "--> Verifying Cloud Storage persistent bucket..."
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  echo "Creating Cloud Storage bucket 'gs://${BUCKET_NAME}' in ${REGION}..."
  gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --uniform-bucket-level-access
fi

# 4. Authenticate Docker with Artifact Registry
echo "--> Configuring Docker credentials..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 5. Build and Push Server Container Image
echo "--> Building UbuntuBio server image..."
docker build \
  --platform linux/amd64 \
  -t "${IMAGE_SERVER}" \
  -f "${REPO_ROOT}/server/Dockerfile" \
  "${REPO_ROOT}/server"

echo "--> Pushing image to Artifact Registry..."
docker push "${IMAGE_SERVER}"

# 6. Render Cloud Run Service YAML with runtime parameters
RENDERED_YAML="${SCRIPT_DIR}/.rendered-cloudrun-service.yaml"
sed \
  -e "s|\${IMAGE_SERVER}|${IMAGE_SERVER}|g" \
  -e "s|\${STORAGE_BUCKET}|${BUCKET_NAME}|g" \
  "${SCRIPT_DIR}/cloudrun-service.yaml" > "${RENDERED_YAML}"

# 7. Deploy to Cloud Run
echo "--> Deploying multi-container service to Cloud Run..."
gcloud run services replace "${RENDERED_YAML}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}"

# 8. Permit Public Ingress
echo "--> Setting IAM policy for public access..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet

rm -f "${RENDERED_YAML}"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")
echo ""
echo "=========================================================="
echo "Deployment Successful!"
echo "Service URL: ${SERVICE_URL}"
echo "Documentation: ${SERVICE_URL}/docs"
echo "Health Check:  ${SERVICE_URL}/healthz"
echo "=========================================================="
