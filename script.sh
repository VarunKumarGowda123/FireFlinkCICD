#!/bin/bash

export usable_machines='["FFE-Muhammad-Abdullah"]'
export interval_seconds=3
export timeout_seconds=15
export CURL_FILE=./curl.txt
# Use a SINGLE QUOTE to hold entire curl
# Use DOUBLE QUOTES *inside* safely

python3 script-cicd.py