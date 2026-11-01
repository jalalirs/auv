#!/usr/bin/env bash
# Builds the router and deploys it as Cloud Run iocean-router (m3ajem,
# us-central1), the service iocean.areen.ai is mapped to. Safe to run twice.
#
#   deployments/gcp/router/deploy.sh
#
# The mapping itself was made once:
#   gcloud beta run domain-mappings create --service iocean-router --domain iocean.areen.ai \
#     --region us-central1 --project m3ajem
# and areen.ai's DNS (Route 53) carries: iocean CNAME ghs.googlehosted.com.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACCOUNT="${IOCEAN_GCP_ACCOUNT:-jalalirs@gmail.com}"

gcloud run deploy iocean-router --source "${HERE}" \
    --project m3ajem --region us-central1 --account "${ACCOUNT}" \
    --allow-unauthenticated --port 8080 \
    --min-instances 0 --max-instances 3 --cpu 1 --memory 256Mi \
    --timeout 900 --quiet
curl -fsS "$(gcloud run services describe iocean-router --project m3ajem --region us-central1 \
    --account "${ACCOUNT}" --format 'value(status.url)')/_router/health"
