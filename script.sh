# bash
#!/bin/bash
set -euo pipefail

export usable_machines='["Varunkumar"]'
export interval_seconds=3
export timeout_seconds=15
export CURL_FILE=./curl.txt

: "${FIREFLINK_TOKEN:?Set FIREFLINK_TOKEN}"

# Optional debug: set DEBUG=1 to print masked confirmation
if [[ "${DEBUG:-0}" == "1" ]]; then
  echo "::add-mask::$FIREFLINK_TOKEN"
  echo "FIREFLINK_TOKEN present"
  echo "FIREFLINK_TOKEN length: ${#FIREFLINK_TOKEN}"
  if command -v sha256sum >/dev/null 2>&1; then
    TOKEN_SHA256=$(printf '%s' "$FIREFLINK_TOKEN" | sha256sum | awk '{print $1}')
  else
    TOKEN_SHA256=$(printf '%s' "$FIREFLINK_TOKEN" | shasum -a 256 | awk '{print $1}')
  fi
  echo "FIREFLINK_TOKEN sha256: $TOKEN_SHA256"
fi

TMP_CURL="$(mktemp)"
sed "s/__ACCESS_TOKEN__/${FIREFLINK_TOKEN//\//\\/}/g" "$CURL_FILE" > "$TMP_CURL"
export CURL_FILE="$TMP_CURL"

python machine_selection.py
rm -f "$TMP_CURL"