#!/usr/bin/env bash
# Deploy ReleaseGate to a Google Compute Engine VM.
#   PROJECT=<id> bash deploy/gcp.sh create           # one time: API, static IP, firewall, VM
#   PROJECT=<id> bash deploy/gcp.sh update [ref]     # build ref (default origin/main); data kept
#   PROJECT=<id> bash deploy/gcp.sh rollback <tag>   # build an earlier tag; data kept
#   PROJECT=<id> bash deploy/gcp.sh status           # VM state and /health of system and tester
# update and rollback then run scripts/post_deploy_check.sh (non-destructive): PASS or FAIL.
# Needs: gcloud signed in, PROJECT set to a project with billing enabled.
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to the Google Cloud project ID}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-us-central1-a}"
VM="${VM:-releasegate}"
MACHINE="${MACHINE:-e2-medium}"
IP_NAME="${VM}-ip"
G=(gcloud --project "$PROJECT" --quiet)
HERE="$(cd "$(dirname "$0")" && pwd)"

ip() { "${G[@]}" compute addresses describe "$IP_NAME" --region "$REGION" --format='value(address)'; }

vm() { "${G[@]}" compute ssh "$VM" --zone "$ZONE" --command "$1"; }

# Check out $1 (a tag, a commit or origin/<branch>) on the VM, rebuild with GIT_SHA set to it,
# then run the post-deploy checks against the new deployment.
deploy_ref() {
  local ref="$1" out prev sha public
  if [[ ! "$ref" =~ ^[A-Za-z0-9._/-]+$ ]]; then
    echo "invalid ref: $ref" >&2
    exit 2
  fi
  out="$(vm "cd /opt/releasegate && sudo git fetch --quiet --tags --force origin \
    && sudo git rev-parse HEAD && sudo git rev-parse --verify '$ref^{commit}'" | tr -d '\r')"
  prev="$(sed -n 1p <<<"$out")"
  sha="$(tail -n 1 <<<"$out")"
  if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "could not resolve $ref on the VM" >&2
    exit 1
  fi
  public="http://$(ip):8080"
  echo "Deploying $ref ($sha); previously deployed: $prev"
  vm "cd /opt/releasegate && sudo git checkout --quiet --detach $sha \
    && sudo GIT_SHA=$sha TESTER_DEFAULT_TARGET=$public docker compose up -d --build \
    && { test -x /usr/sbin/cron || { sudo apt-get update -qq && sudo apt-get install -y -qq cron; }; } \
    && sudo install -m 0644 deploy/releasegate-backup.cron /etc/cron.d/releasegate-backup"
  if [ "$(git -C "$HERE/.." rev-parse HEAD)" != "$sha" ]; then
    echo "Note: this checkout isn't at $sha, and the checks read the contract from it."
  fi
  if bash "$HERE/../scripts/post_deploy_check.sh" "http://$(ip):8080" "$sha" \
    --test-endpoints "${TEST_ENDPOINTS:-on}"; then
    echo "Deploy of $sha: PASS. Record it in docs/test-reports/; tag it if it's a milestone."
  else
    echo "Deploy of $sha: FAIL. Roll back with: bash deploy/gcp.sh rollback <previous tag>" \
      "(previous commit $prev)" >&2
    exit 1
  fi
}

case "${1:-}" in
  create)
    "${G[@]}" services enable compute.googleapis.com
    "${G[@]}" compute addresses create "$IP_NAME" --region "$REGION"
    "${G[@]}" compute firewall-rules create "${VM}-allow-8080" \
      --network default --direction INGRESS --allow tcp:8080 \
      --source-ranges 0.0.0.0/0 --target-tags "$VM"
    "${G[@]}" compute firewall-rules create "${VM}-allow-8081" \
      --network default --direction INGRESS --allow tcp:8081 \
      --source-ranges 0.0.0.0/0 --target-tags "$VM"
    "${G[@]}" compute instances create "$VM" \
      --zone "$ZONE" --machine-type "$MACHINE" \
      --image-family debian-12 --image-project debian-cloud \
      --boot-disk-size 20GB --boot-disk-type pd-balanced \
      --address "$(ip)" --tags "$VM" \
      --metadata-from-file startup-script="$HERE/gcp-startup.sh" \
      --metadata enable-test-endpoints=true,repo-branch=main
    echo "System: http://$(ip):8080  Tester: http://$(ip):8081  (first boot takes ~3-5 min)"
    ;;
  update)
    deploy_ref "${2:-origin/main}"
    ;;
  rollback)
    deploy_ref "refs/tags/${2:?usage: deploy/gcp.sh rollback <tag>}"
    ;;
  status)
    "${G[@]}" compute instances describe "$VM" --zone "$ZONE" --format='value(status)'
    for port in 8080 8081; do
      printf 'http://%s:%s  ' "$(ip)" "$port"
      curl -s --max-time 5 "http://$(ip):$port/health" || printf '(not answering)'
      echo
    done
    ;;
  *)
    sed -n '2,8p' "$0"
    exit 1
    ;;
esac
