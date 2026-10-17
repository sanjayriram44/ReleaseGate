#!/usr/bin/env bash
# Deploy ReleaseGate to a Google Compute Engine VM.
#   PROJECT=<id> bash deploy/gcp.sh create   # one time: API, static IP, firewall (8080, 8081), VM
#   PROJECT=<id> bash deploy/gcp.sh update   # pull latest main on the VM and rebuild; data kept
#   PROJECT=<id> bash deploy/gcp.sh status   # VM state and /health of system and tester
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
    "${G[@]}" compute ssh "$VM" --zone "$ZONE" --command \
      'cd /opt/releasegate && sudo git pull --ff-only && sudo docker compose up -d --build && sudo git log -1 --oneline'
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
    sed -n '2,6p' "$0"
    exit 1
    ;;
esac
