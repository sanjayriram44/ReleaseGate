#!/usr/bin/env bash
# Manual smoke test of the running API. WARNING: calls /test/reset, which wipes all data.
# Usage: bash scripts/smoke.sh [host:port]    (server needs ENABLE_TEST_ENDPOINTS=true)
B="${1:-localhost:8080}"
H='X-User-Id: alice'
J='content-type: application/json'
FAILS=0

# check <label> <expected status> <curl args...>  -> prints PASS/FAIL, leaves body in $BODY
check() {
  local label="$1" want="$2"; shift 2
  local out code
  out=$(curl -s -w $'\n%{http_code}' "$@")
  code="${out##*$'\n'}"
  BODY="${out%$'\n'*}"
  if [ "$code" = "$want" ]; then
    printf 'PASS  %-58s %s\n' "$label" "$code"
  else
    printf 'FAIL  %-58s got %s, want %s\n      %s\n' "$label" "$code" "$want" "$BODY"
    FAILS=$((FAILS + 1))
  fi
}
field() { python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }
expect_in_body() {
  case "$BODY" in *"$1"*) ;; *) printf 'FAIL  body should contain: %s\n      %s\n' "$1" "$BODY"; FAILS=$((FAILS + 1));; esac
}

NEW_SBOM='{"bomFormat":"CycloneDX","specVersion":"1.6","version":1,"components":[{"type":"library","name":"only-one","version":"1.0.0"}]}'

check "reset" 204 -X POST "$B/api/v1/test/reset"
check "set clock to 2026-11-01T23:59:59Z" 200 -X PUT "$B/api/v1/test/clock" -H "$J" -d '{"now":"2026-11-01T23:59:59Z"}'
check "clock rejects non-UTC offset" 400 -X PUT "$B/api/v1/test/clock" -H "$J" -d '{"now":"2026-11-01T23:59:59+02:00"}'

echo "--- AC-01"
check "past release" 201 -X POST "$B/api/v1/releases" -H "$H" -H "$J" -d '{"product":"ExampleRouter","version":"1.0.0","support_end_date":"2026-10-31"}'
expect_in_body '"support_status":"unsupported"'
check "boundary release (end date = today)" 201 -X POST "$B/api/v1/releases" -H "$H" -H "$J" -d '{"product":"ExampleRouter","version":"2.0.0","support_end_date":"2026-11-01"}'
expect_in_body '"support_status":"supported"'
A=$(echo "$BODY" | field '["release_id"]')
check "future release" 201 -X POST "$B/api/v1/releases" -H "$H" -H "$J" -d '{"product":"ExampleRouter","version":"3.0.0","support_end_date":"2026-11-02"}'
expect_in_body '"support_status":"supported"'
check "missing support_end_date" 400 -X POST "$B/api/v1/releases" -H "$H" -H "$J" -d '{"product":"ExampleRouter","version":"4.0.0"}'
expect_in_body 'support_end_date is required'
check "duplicate product+version" 409 -X POST "$B/api/v1/releases" -H "$H" -H "$J" -d '{"product":"ExampleRouter","version":"2.0.0","support_end_date":"2030-01-01"}'
check "missing X-User-Id" 400 -X POST "$B/api/v1/releases" -H "$J" -d '{}'
check "GET release" 200 "$B/api/v1/releases/$A"
check "GET unknown release" 404 "$B/api/v1/releases/nope"
check "register second release (no SBOM)" 201 -X POST "$B/api/v1/releases" -H "$H" -H "$J" -d '{"product":"ExampleGateway","version":"9.9.9","support_end_date":"2030-01-01"}'
B2=$(echo "$BODY" | field '["release_id"]')

echo "--- AC-02"
check "upload 25-component SBOM" 200 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" --data-binary @fixtures/sbom_25_components.json
expect_in_body '"component_count":25'
check "components of release with SBOM" 200 "$B/api/v1/releases/$A/components"
[ "$(echo "$BODY" | field '["components"].__len__()')" = 25 ] && echo "PASS  25 components returned" || { echo "FAIL  expected 25 components"; FAILS=$((FAILS + 1)); }
check "components of release without SBOM" 200 "$B/api/v1/releases/$B2/components"
[ "$(echo "$BODY" | field '["components"].__len__()')" = 0 ] && echo "PASS  0 components returned" || { echo "FAIL  expected 0 components"; FAILS=$((FAILS + 1)); }
check "components of unknown release" 404 "$B/api/v1/releases/nope/components"

echo "--- AC-03"
check "malformed JSON" 400 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" -d '{"bomFormat":"CycloneDX", '
expect_in_body 'not valid JSON'
check "missing bomFormat" 400 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" -d '{"specVersion":"1.6","version":1,"components":[]}'
expect_in_body 'missing required field: bomFormat'
check "plaintext" 400 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" -d 'plain text'
expect_in_body 'not valid JSON'
check "unsupported specVersion" 400 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" -d '{"bomFormat":"CycloneDX","specVersion":"1.3","version":1}'
check "component missing version" 400 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" -d '{"bomFormat":"CycloneDX","specVersion":"1.6","version":1,"components":[{"type":"library","name":"x"}]}'
check "unregistered release" 404 -X PUT "$B/api/v1/releases/rel-fake/sbom" -H "$H" -H "$J" -d "$NEW_SBOM"
check "SBOM upload without X-User-Id" 400 -X PUT "$B/api/v1/releases/$A/sbom" -H "$J" -d "$NEW_SBOM"
check "components untouched after rejections" 200 "$B/api/v1/releases/$A/components"
[ "$(echo "$BODY" | field '["components"].__len__()')" = 25 ] && echo "PASS  still 25 components" || { echo "FAIL  components changed"; FAILS=$((FAILS + 1)); }

echo "--- replace + clock"
check "replace SBOM" 200 -X PUT "$B/api/v1/releases/$A/sbom" -H "$H" -H "$J" -d "$NEW_SBOM"
expect_in_body '"component_count":1'
check "components after replace" 200 "$B/api/v1/releases/$A/components"
expect_in_body 'only-one'
check "set clock one second past boundary" 200 -X PUT "$B/api/v1/test/clock" -H "$J" -d '{"now":"2026-11-02T00:00:00Z"}'
check "boundary release is now unsupported" 200 "$B/api/v1/releases/$A"
expect_in_body '"support_status":"unsupported"'

echo "--- audit"
check "GET audit log" 200 "$B/api/v1/audit-logs"
echo "$BODY" | python3 -c 'import sys,json;[print("      ",e["action"],e["user_id"],e["entity_id"]) for e in json.load(sys.stdin)["events"]]'
EID=$(echo "$BODY" | field '["events"][0]["event_id"]')
check "PATCH audit entry" 405 -X PATCH "$B/api/v1/audit-logs/$EID" -H "$H"
check "DELETE audit entry" 405 -X DELETE "$B/api/v1/audit-logs/$EID" -H "$H"

echo "--- reset + health"
check "reset" 204 -X POST "$B/api/v1/test/reset"
check "audit log empty after reset" 200 "$B/api/v1/audit-logs"
expect_in_body '"events":[]'
check "release gone after reset" 404 "$B/api/v1/releases/$A"
check "health" 200 "$B/health"

echo
if [ "$FAILS" = 0 ]; then echo "ALL CHECKS PASSED"; else echo "$FAILS CHECK(S) FAILED"; exit 1; fi
