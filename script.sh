# bash
#!/bin/bash
set -euo pipefail

export usable_machines='["Varunkumar"]'
export interval_seconds=3
export timeout_seconds=15
export CURL_FILE=./curl.txt

: "${FIREFLINK_TOKEN:?Set FIREFLINK_TOKEN (e.g. from GitHub secret)}"

TMP_CURL="$(mktemp)"
sed "s/__ACCESS_TOKEN__/${FIREFLINK_TOKEN//\//\\/}/g" "$CURL_FILE" > "$TMP_CURL"
export CURL_FILE="$TMP_CURL"

python machine_selection.py
rm -f "$TMP_CURL"