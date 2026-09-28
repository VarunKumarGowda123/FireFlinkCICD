import json
import re
import requests
import copy
import time
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

def _require_env(name):

    value = os.getenv(name)

    if not value:

        raise SystemExit(
            f"Missing required environment variable: {name}"
        )

    return value


# Usable machine allow-list (JSON array of client IDs)
_usable_machines_raw = os.getenv("usable_machines", "[]")
try:

    USABLE_MACHINES = json.loads(_usable_machines_raw)

except json.JSONDecodeError:

    raise SystemExit(
        "Invalid usable_machines value. "
        "Expected a JSON array of machine client IDs."
    )

if not isinstance(USABLE_MACHINES, list):

    raise SystemExit(
        "usable_machines must be a JSON array."
    )

# Time settings
INTERVAL_SECONDS = int(_require_env("interval_seconds"))
RESULT_POLL_INTERVAL_SECONDS = INTERVAL_SECONDS
EXECUTION_TIMEOUT_SECONDS = int(_require_env("timeout_seconds"))
MACHINE_TIMEOUT_SECONDS = int(
    os.getenv(
        "machine_timeout_seconds",
        "15"
    )
)

# Generated curl file
CURL_FILE_PATH = _require_env("CURL_FILE")

with open(
    CURL_FILE_PATH,
    encoding="utf-8"
) as curl_file:

    CURL_STRING = curl_file.read()

# Shared request settings
REQUEST_TIMEOUT_SECONDS = int(
    os.getenv(
        "request_timeout_seconds",
        "30"
    )
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
)


# ============================================================
# PARSE CURL
# ============================================================

def parse_curl(curl_str):

    url_match = re.search(
        r"curl\s+--location\s+'([^\"]+)'",
        curl_str
    )

    url = url_match.group(1) if url_match else None

    json_match = re.search(
        r'--data-raw\s+"({[\s\S]*?})"',
        curl_str
    )

    if not json_match:

        raise ValueError("JSON not found in curl command")

    json_str = json_match.group(1)
    json_str = json_str.encode("utf-8").decode("unicode_escape")

    try:

        data = json.loads(json_str)

    except ValueError:

        raise SystemExit("Failed to parse CURL command")

    header_template = {
        "clientId": "",
        "executionDataSet": {},
        "machineInstances": []
    }

    selected_machines = (
        data.get("executionSettings", {})
        .get("machines", {})
        .get("selectedMachines", [])
    )

    if (
        selected_machines
        and isinstance(selected_machines[0], dict)
        and selected_machines[0].get("executionDataSet")
    ):

        header_template["executionDataSet"] = copy.deepcopy(
            selected_machines[0]["executionDataSet"]
        )

    return {
        "url": url,
        "projectId": data.get("projectId"),
        "accessToken": data.get("accessToken"),
        "licenseId": data.get("licenseId"),
        "suiteId": data.get("suiteId"),
        "waitConfig": data.get("waitConfig"),
        "headerTemplate": header_template,
    }


def get_base_url(execution_url):

    if not execution_url:

        raise SystemExit(
            "Execution URL not found in CURL file."
        )

    parsed_url = urlparse(execution_url)

    if not parsed_url.scheme or not parsed_url.netloc:

        raise SystemExit(
            "Invalid execution URL in CURL file."
        )

    return f"{parsed_url.scheme}://{parsed_url.netloc}"


parsed_data = parse_curl(CURL_STRING)
BASE_URL = get_base_url(parsed_data["url"])
header_template = parsed_data["headerTemplate"]


# ============================================================
# FETCH MACHINES CONFIGURED IN SUITE
# ============================================================

def fetch_selected_machines(
    suite_id,
    access_token,
    project_id
):

    url = (
        f"{BASE_URL}/"
        f"project/optimize/v3/suites/{suite_id}"
    )

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": USER_AGENT,
        "authorization": f"Bearer {access_token}",
        "projectid": project_id,
        "sec-ch-ua": (
            '"Chromium";v="142", '
            '"Microsoft Edge";v="142", '
            '"Not_A Brand";v="99"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS
        )

    except requests.RequestException as exc:

        raise SystemExit(
            f"Failed to fetch suite details: {exc}"
        )

    print(
        f"Suite API Status Code: {response.status_code}"
    )

    if response.status_code == 401:

        raise SystemExit(
            "401 Unauthorized — "
            "Invalid or expired access token."
        )

    if response.status_code == 403:

        raise SystemExit(
            "403 Forbidden — You don't have permission."
        )

    if response.status_code == 404:

        raise SystemExit(
            f"404 Not Found — URL not found: {url}"
        )

    if response.status_code >= 500:

        raise SystemExit(
            "Server error while fetching suite."
        )

    if response.status_code != 200:

        raise SystemExit(
            f"Unexpected status code "
            f"{response.status_code}"
        )

    try:

        data = response.json()

    except ValueError:

        raise SystemExit(
            "Failed to parse suite API JSON."
        )

    try:

        machines = (
            data["responseObject"]
            ["executionSettings"]
            ["machines"]
            ["selectedMachines"]
        )

    except KeyError:

        raise SystemExit(
            "selectedMachines not found in suite response."
        )

    selected_ids = []

    machine_instances = []

    for machine in machines:

        client_id = machine["clientId"]

        selected_ids.append(client_id)

        machine_instances.append({
            "clientId": client_id,
            "machineInstances": copy.deepcopy(
                machine.get("machineInstances", [])
            )
        })

    print("\nConfigured machines:")

    for machine_id in selected_ids:

        print(f"  - {machine_id}")

    return selected_ids, machine_instances


# ============================================================
# FETCH ACTIVE MACHINE STATUS
# ============================================================

def fetch_active_machines(
    access_token,
    license_id
):

    url = (
        f"{BASE_URL}/"
        "project/optimize/v3/client-system-config/"
        "machine-status"
    )

    headers = {
        "Accept": "*/*",
        "Accept-Language": (
            "en-GB,en;q=0.9,en-US;q=0.8"
        ),
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": USER_AGENT,
        "authorization": f"Bearer {access_token}",
        "licenseId": license_id
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS
        )

    except requests.RequestException as exc:

        print(
            f"❌ Machine status request failed: {exc}"
        )

        return [], []

    status = response.status_code

    if status == 401:

        raise SystemExit(
            "401 Unauthorized — "
            "Invalid or expired access token."
        )

    if status == 403:

        raise SystemExit(
            "403 Forbidden — You don't have access."
        )

    if status == 404:

        raise SystemExit(
            f"404 Not Found — URL not found: {url}"
        )

    if status >= 500:

        print(
            f"❌ Machine status server error: {status}"
        )

        return [], []

    if status != 200:

        print(
            f"❌ Unexpected machine status: {status}"
        )

        return [], []

    try:

        data = response.json()

    except ValueError:

        print(
            "❌ Failed to parse machine status response."
        )

        return [], []

    machines = (
        data
        .get("responseObject", {})
        .get("clientSystems", [])
    )

    available_machines = []

    available_client_ids = []

    for machine in machines:

        if machine.get("status") != "Active":

            continue

        client_id = machine.get("clientId")

        machine_info = machine.get(
            "machine",
            {}
        )

        available_machines.append({
            "clientId": client_id,
            "status": "Active",
            "machineInfo": machine_info
        })

        available_client_ids.append(
            client_id
        )

    return (
        available_machines,
        available_client_ids
    )


# ============================================================
# FILTER USABLE MACHINES
# ============================================================

def filter_usable_machines(
    selected_ids,
    machine_instances
):

    if not USABLE_MACHINES:

        return selected_ids, machine_instances

    allowed_ids = set(USABLE_MACHINES)

    filtered_ids = [
        machine_id
        for machine_id in selected_ids
        if machine_id in allowed_ids
    ]

    filtered_instances = [
        machine
        for machine in machine_instances
        if machine["clientId"] in allowed_ids
    ]

    if not filtered_ids:

        raise SystemExit(
            "No suite machines match usable_machines "
            "from environment configuration."
        )

    print("\nUsable machines filter applied:")

    for machine_id in filtered_ids:

        print(f"  - {machine_id}")

    return filtered_ids, filtered_instances


# ============================================================
# BUILD MACHINE EXECUTION HEADERS
# ============================================================

def build_machine_headers(
    selected_machines,
    header_template,
    instance_selected,
    available_machines
):

    header_inclusion = []

    for machine_id in selected_machines:

        # ----------------------------------------------------
        # Find exact configured machine
        # ----------------------------------------------------

        active_machine = next(
            (
                machine
                for machine in available_machines
                if machine["clientId"] == machine_id
            ),
            None
        )

        if active_machine is None:

            raise Exception(
                f"Configured machine {machine_id} "
                f"is not active."
            )

        machine_info = active_machine[
            "machineInfo"
        ]

        # ----------------------------------------------------
        # Copy header
        # ----------------------------------------------------

        header = copy.deepcopy(
            header_template
        )

        # ----------------------------------------------------
        # Find instances for EXACT configured machine
        # ----------------------------------------------------

        machine_instances = next(
            (
                copy.deepcopy(
                    item["machineInstances"]
                )
                for item in instance_selected
                if item["clientId"] == machine_id
            ),
            []
        )

        # ----------------------------------------------------
        # Update instances
        # ----------------------------------------------------

        for instance in machine_instances:

            instance["clientId"] = machine_id

            instance["machineInfo"] = (
                machine_info
            )

        # ----------------------------------------------------
        # Update header
        # ----------------------------------------------------

        header["clientId"] = machine_id

        header["machineInstances"] = (
            machine_instances
        )

        header_inclusion.append(
            header
        )

    return header_inclusion


# ============================================================
# TRIGGER EXECUTION
#
# IMPORTANT:
# This function is called ONLY ONCE.
# ============================================================

def trigger_execution(
    url_exe,
    suite_id,
    wait_config,
    license_id,
    access_token,
    project_id,
    header_inclusion
):

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {

        "suiteId": suite_id,

        "waitConfig": wait_config,

        "licenseId": license_id,

        "accessToken": access_token,

        "projectId": project_id,

        "executionSettings": {

            "machines": {

                "multiple": "",

                "executionType": "SEQUENTIAL",

                "selectedMachines":
                    header_inclusion
            }
        }
    }

    print(
        "\n=================================================="
    )

    print(
        "🚀 TRIGGERING EXECUTION"
    )

    print(
        "=================================================="
    )

    try:

        response = requests.post(
            url_exe,
            headers=headers,
            json=payload,
            timeout=60
        )

    except requests.RequestException as exc:

        return {
            "status_code": None,
            "response_json": None,
            "raw": None,
            "execution_id": None,
            "error": str(exc)
        }

    try:

        response_json = response.json()

    except ValueError:

        response_json = None

    print(
        f"Execution API Status Code: "
        f"{response.status_code}"
    )

    execution_id = None

    if response_json:

        execution_id = (
            response_json.get("executionId")
        )

    return {

        "status_code":
            response.status_code,

        "response_json":
            response_json,

        "raw":
            response.text,

        "execution_id":
            execution_id
    }


# ============================================================
# FIND PERCENTAGE IN RESULT RESPONSE
# ============================================================

def find_percentage(data):

    """
    Recursively searches the result JSON for common
    percentage field names.

    This allows the script to work even if the percentage
    is nested inside responseObject/result/overview/etc.
    """

    percentage_keys = {
        "percentage",
        "passPercentage",
        "passedPercentage",
        "executionPercentage",
        "resultPercentage",
        "successPercentage",
        "passPercent",
        "passedPercent"
    }

    if isinstance(data, dict):

        # First check direct keys
        for key, value in data.items():

            normalized_key = (
                str(key)
                .replace("_", "")
                .replace("-", "")
                .lower()
            )

            normalized_percentage_keys = {
                str(item)
                .replace("_", "")
                .replace("-", "")
                .lower()
                for item in percentage_keys
            }

            if (
                normalized_key
                in normalized_percentage_keys
            ):

                if isinstance(
                    value,
                    (int, float)
                ):

                    return value

                if isinstance(
                    value,
                    str
                ):

                    try:

                        return float(
                            value.replace(
                                "%",
                                ""
                            ).strip()
                        )

                    except ValueError:

                        pass

        # Search nested objects
        for value in data.values():

            result = find_percentage(
                value
            )

            if result is not None:

                return result

    elif isinstance(data, list):

        for item in data:

            result = find_percentage(
                item
            )

            if result is not None:

                return result

    return None


# ============================================================
# FIND EXECUTION STATUS
# ============================================================

def find_execution_status(data):

    """
    Searches recursively for a status field.
    """

    status_keys = {
        "status",
        "executionStatus",
        "executionstatus",
        "state"
    }

    if isinstance(data, dict):

        for key, value in data.items():

            if str(key).lower() in {
                item.lower()
                for item in status_keys
            }:

                if isinstance(
                    value,
                    str
                ):

                    return value

        for value in data.values():

            result = find_execution_status(
                value
            )

            if result is not None:

                return result

    elif isinstance(data, list):

        for item in data:

            result = find_execution_status(
                item
            )

            if result is not None:

                return result

    return None


# ============================================================
# FORMAT EXECUTION RESULT (CI-STYLE OUTPUT)
# ============================================================

def _safe_dict(value):
    """Return value when it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def _collect_run_results(result_json):
    """Collect all runResults entries across every machine."""
    response_object = _safe_dict(result_json.get("responseObject"))
    machines = response_object.get("machines") or []

    run_results = []

    for machine in machines:
        if not isinstance(machine, dict):
            continue

        for run_result in machine.get("runResults") or []:
            if isinstance(run_result, dict):
                run_results.append(run_result)

    return run_results


def extract_result_stats(result_json):
    """
    Extract pass/fail/warning/skipped/terminated percentages
    from the execution result API response.
    Aggregates stats across all machines and run results.
    """
    stats = {
        "passed": 0.0,
        "failed": 0.0,
        "warning": 0.0,
        "skipped": 0.0,
        "terminated": 0.0,
    }

    if not result_json:
        return stats

    try:
        run_results = _collect_run_results(result_json)

        if not run_results:
            return stats

        totals = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warning": 0,
            "skipped": 0,
            "terminated": 0,
        }

        percentage_samples = []

        for run_result in run_results:
            script_stats = _safe_dict(run_result.get("scriptStats"))
            script_total = script_stats.get("total") or 0

            if script_total > 0:
                totals["total"] += script_total
                totals["passed"] += script_stats.get("totalPassed") or 0
                totals["failed"] += script_stats.get("totalFailed") or 0
                totals["warning"] += script_stats.get("totalWarning") or 0
                totals["skipped"] += script_stats.get("totalSkipped") or 0
                totals["terminated"] += script_stats.get("totalTerminated") or 0
                continue

            result_pct = _safe_dict(run_result.get("resultPercentage"))
            if result_pct:
                percentage_samples.append(result_pct)

        if totals["total"] > 0:
            stats["passed"] = round((totals["passed"] / totals["total"]) * 100, 1)
            stats["failed"] = round((totals["failed"] / totals["total"]) * 100, 1)
            stats["warning"] = round((totals["warning"] / totals["total"]) * 100, 1)
            stats["skipped"] = round((totals["skipped"] / totals["total"]) * 100, 1)
            stats["terminated"] = round(
                (totals["terminated"] / totals["total"]) * 100, 1
            )
            return stats

        if percentage_samples:
            sample_count = len(percentage_samples)
            stats["passed"] = round(
                sum(float(s.get("passed") or 0.0) for s in percentage_samples)
                / sample_count,
                1,
            )
            stats["failed"] = round(
                sum(float(s.get("failed") or 0.0) for s in percentage_samples)
                / sample_count,
                1,
            )
            stats["warning"] = round(
                sum(float(s.get("warning") or 0.0) for s in percentage_samples)
                / sample_count,
                1,
            )
            stats["skipped"] = round(
                sum(float(s.get("skipped") or 0.0) for s in percentage_samples)
                / sample_count,
                1,
            )

    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        pass

    return stats


def determine_result_status(stats):
    """Return PASS or FAIL like the FireFlink action jar."""
    if stats["failed"] > 0 or stats["terminated"] > 0:
        return "FAIL"
    if stats["passed"] == 100.0:
        return "PASS"
    return "FAIL"


def format_execution_report(execution_id, result_json):
    """Format output like fireflink-action GitHub log."""
    stats = extract_result_stats(result_json)
    result_status = determine_result_status(stats)

    detail_url = (
        f"{BASE_URL}/dashboardexecution/optimize/v1/"
        f"dashboard/execution/{execution_id}"
    )

    lines = [
        f"Suite execution detail URL: {detail_url}",
        "Execution Status.: Initialized",
        "Execution Status.: Completed",
        f"Execution status: Completed, result Status:{result_status}",
        "",
        "| Passed | Failed | Warning | Skipped | Terminated |",
        (
            f"| {stats['passed']:.0f}% "
            f"| {stats['failed']:.0f}% "
            f"| {stats['warning']:.0f}% "
            f"| {stats['skipped']:.0f}% "
            f"| {stats['terminated']:.0f}% |"
        ),
        "",
        "EXECUTION PASSED" if result_status == "PASS" else "EXECUTION FAILED",
    ]

    return "\n".join(lines)


# ============================================================
# GET EXECUTION RESULT
# ============================================================

def fetch_execution_result(
    execution_id,
    access_token,
    project_id
):

    url = (
        f"{BASE_URL}/"
        "executionresult/optimize/v3/"
        "execution-result/"
        f"test-execution-overview/"
        f"{execution_id}/execution/"
        f"{execution_id}"
        "?runId="
    )

    headers = {

        "Accept": "*/*",

        "Accept-Language":
            "en-US,en;q=0.9",

        "Connection":
            "keep-alive",

        "authorization":
            f"Bearer {access_token}",

        "licensetype":
            "C-Professional",

        "projectid":
            project_id,

        "projectname":
            "Suite and Integration",

        "projecttype":
            "Multi-Channel",

        "timezone":
            "Asia/Tehran",

        "User-Agent":
            (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/148.0.0.0 "
                "Safari/537.36"
            )
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=60
        )

    except requests.RequestException as exc:

        return {

            "success": False,

            "status_code": None,

            "response_json": None,

            "error": str(exc)
        }

    if response.status_code == 401:

        return {

            "success": False,

            "status_code": 401,

            "response_json": None,

            "error":
                "401 Unauthorized — "
                "Access token is invalid or expired."
        }

    if response.status_code == 403:

        return {

            "success": False,

            "status_code": 403,

            "response_json": None,

            "error":
                "403 Forbidden — "
                "No permission to access execution result."
        }

    if response.status_code == 404:

        return {

            "success": False,

            "status_code": 404,

            "response_json": None,

            "error":
                f"Execution result not found "
                f"for {execution_id}."
        }

    if response.status_code >= 500:

        return {

            "success": False,

            "status_code":
                response.status_code,

            "response_json": None,

            "error":
                "Execution result server error."
        }

    try:

        response_json = response.json()

    except ValueError:

        return {

            "success": False,

            "status_code":
                response.status_code,

            "response_json": None,

            "error":
                "Execution result response "
                "is not valid JSON."
        }

    return {

        "success":
            response.status_code == 200,

        "status_code":
            response.status_code,

        "response_json":
            response_json
    }


# ============================================================
# WAIT FOR EXECUTION RESULT
# ============================================================

def poll_execution_result(
    execution_id,
    access_token,
    project_id,
    timeout_seconds,
    interval_seconds
):

    print(
        "\n=================================================="
    )

    print(
        f"🔎 Checking result for execution: "
        f"{execution_id}"
    )

    print(
        "=================================================="
    )

    start_time = time.time()

    attempts = 0

    while True:

        attempts += 1

        print(
            f"\n🔄 Result polling attempt #{attempts}"
        )

        result_response = fetch_execution_result(
            execution_id=execution_id,
            access_token=access_token,
            project_id=project_id
        )

        if not result_response["success"]:

            print(
                f"⚠️ Result API returned: "
                f"{result_response.get('status_code')}"
            )

            print(
                f"⚠️ {result_response.get('error')}"
            )

        else:

            result_json = (
                result_response["response_json"]
            )

            print(
                "✅ Result API response received."
            )

            # ------------------------------------------------
            # Find execution status
            # ------------------------------------------------

            execution_status = (
                find_execution_status(
                    result_json
                )
            )

            if execution_status:

                print(
                    f"Execution status: "
                    f"{execution_status}"
                )

            # ------------------------------------------------
            # Find percentage
            # ------------------------------------------------

            percentage = find_percentage(
                result_json
            )

            if percentage is not None:

                print(
                    f"\n✅ Execution result percentage: "
                    f"{percentage}%"
                )

                stats = extract_result_stats(result_json)

                return {

                    "executionId":
                        execution_id,

                    "percentage":
                        percentage,

                    "result":
                        result_json,

                    "stats":
                        stats,

                    "resultStatus":
                        determine_result_status(stats),
                }

            # ------------------------------------------------
            # Print response when percentage isn't available
            # ------------------------------------------------

            print(
                "⏳ Execution result is not available yet."
            )

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        elapsed = time.time() - start_time

        if elapsed >= timeout_seconds:

            print(
                "\n⛔ Execution result timeout reached."
            )

            return {

                "executionId":
                    execution_id,

                "percentage":
                    None,

                "result":
                    None,

                "error":
                    (
                        "Execution result was not "
                        "available before timeout."
                    ),

                "resultStatus":
                    "FAIL",
            }

        print(
            f"⏳ Waiting {interval_seconds} seconds "
            f"before checking result again..."
        )

        time.sleep(
            interval_seconds
        )


# ============================================================
# WAIT FOR CONFIGURED MACHINES
# ============================================================

def wait_for_configured_machines(
    selected_machines,
    machine_instances
):

    print(
        "\n=================================================="
    )

    print(
        "🔍 CHECKING CONFIGURED MACHINES"
    )

    print(
        "=================================================="
    )

    start_time = time.time()

    attempts = 0

    while True:

        attempts += 1

        print(
            f"\n🔄 Machine polling attempt #{attempts}"
        )

        (
            available_machines,
            available_client_ids
        ) = fetch_active_machines(
            access_token=
                parsed_data["accessToken"],

            license_id=
                parsed_data["licenseId"]
        )

        unavailable_machines = []

        for machine_id in selected_machines:

            if machine_id in available_client_ids:

                print(
                    f"  ✅ {machine_id} -> ACTIVE"
                )

            else:

                print(
                    f"  ❌ {machine_id} -> NOT ACTIVE"
                )

                unavailable_machines.append(
                    machine_id
                )

        # ----------------------------------------------------
        # ALL configured machines are active
        # ----------------------------------------------------

        if not unavailable_machines:

            print(
                "\n✅ ALL configured machines are ACTIVE."
            )

            print(
                "✅ No replacement machine will be used."
            )

            header_inclusion = (
                build_machine_headers(
                    selected_machines,
                    header_template,
                    machine_instances,
                    available_machines
                )
            )

            return header_inclusion

        # ----------------------------------------------------
        # Check machine timeout
        # ----------------------------------------------------

        elapsed = (
            time.time()
            - start_time
        )

        if elapsed >= MACHINE_TIMEOUT_SECONDS:

            print(
                "\n⛔ MACHINE TIMEOUT REACHED."
            )

            print(
                "❌ Execution will NOT be triggered."
            )

            print(
                "❌ Unavailable configured machines:"
            )

            for machine_id in unavailable_machines:

                print(
                    f"   - {machine_id}"
                )

            return None

        print(
            f"\n⏳ Waiting "
            f"{INTERVAL_SECONDS} seconds..."
        )

        time.sleep(
            INTERVAL_SECONDS
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n=================================================="
    )

    print(
        "🔥 FireFlink Machine Execution"
    )

    print(
        "=================================================="
    )

    # --------------------------------------------------------
    # Validate token
    # --------------------------------------------------------

    if not parsed_data.get("accessToken"):

        raise SystemExit(
            "\n❌ accessToken not found in CURL file.\n"
            "Check the CURL_FILE content."
        )

    if not parsed_data.get("suiteId"):

        raise SystemExit(
            "\n❌ suiteId not found in CURL file."
        )

    if not parsed_data.get("projectId"):

        raise SystemExit(
            "\n❌ projectId not found in CURL file."
        )

    # --------------------------------------------------------
    # STEP 1
    # Get configured machines from suite
    # --------------------------------------------------------

    (
        selected_ids,
        machine_instances
    ) = fetch_selected_machines(
        suite_id=
            parsed_data["suiteId"],

        access_token=
            parsed_data["accessToken"],

        project_id=
            parsed_data["projectId"]
    )

    (
        selected_ids,
        machine_instances
    ) = filter_usable_machines(
        selected_ids,
        machine_instances
    )

    # --------------------------------------------------------
    # STEP 2
    # Wait for EXACT configured machines
    # --------------------------------------------------------

    header_inclusion = (
        wait_for_configured_machines(
            selected_machines=
                selected_ids,

            machine_instances=
                machine_instances
        )
    )

    # --------------------------------------------------------
    # Machines did not become active
    # --------------------------------------------------------

    if header_inclusion is None:

        print("\nEXECUTION FAILED")
        print("Error: Configured machines did not become active.")

        final_result = {
            "executionId": None,
            "resultStatus": "FAIL",
            "status": "MACHINE_TIMEOUT",
        }

        return final_result

    # --------------------------------------------------------
    # STEP 3
    # Trigger execution ONCE
    # --------------------------------------------------------

    execution_response = (
        trigger_execution(
            url_exe=
                parsed_data["url"],

            suite_id=
                parsed_data["suiteId"],

            wait_config=
                parsed_data["waitConfig"],

            license_id=
                parsed_data["licenseId"],

            access_token=
                parsed_data["accessToken"],

            project_id=
                parsed_data["projectId"],

            header_inclusion=
                header_inclusion
        )
    )

    # --------------------------------------------------------
    # STEP 4
    # Get execution ID
    # --------------------------------------------------------

    execution_id = (
        execution_response.get(
            "execution_id"
        )
    )

    if not execution_id:

        print("\nEXECUTION FAILED")
        print("Error: Failed to trigger execution.")

        final_result = {
            "executionId": None,
            "resultStatus": "FAIL",
            "status": "EXECUTION_TRIGGER_FAILED",
        }

        return final_result

    print(
        "\n=================================================="
    )

    print(
        f"✅ EXECUTION STARTED"
    )

    print(
        f"Execution ID: {execution_id}"
    )

    print(
        "=================================================="
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # DO NOT CALL trigger_execution() AGAIN.
    #
    # From this point we ONLY use execution_id.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # STEP 5
    # Poll execution result API
    # --------------------------------------------------------

    execution_result = (
        poll_execution_result(
            execution_id=
                execution_id,

            access_token=
                parsed_data["accessToken"],

            project_id=
                parsed_data["projectId"],

            timeout_seconds=
                EXECUTION_TIMEOUT_SECONDS,

            interval_seconds=
                RESULT_POLL_INTERVAL_SECONDS
        )
    )

    # --------------------------------------------------------
    # STEP 6
    # Final result — CI-style report
    # --------------------------------------------------------

    result_json = execution_result.get("result")

    print(
        "\n=================================================="
    )

    print(
        "🎯 FINAL RESULT"
    )

    print(
        "=================================================="
    )

    if result_json:

        report = format_execution_report(execution_id, result_json)
        print(report)

        stats = extract_result_stats(result_json)
        result_status = determine_result_status(stats)

        final_result = {
            "executionId": execution_id,
            "executionUrl": (
                f"{BASE_URL}/dashboardexecution/optimize/v1/"
                f"dashboard/execution/{execution_id}"
            ),
            "resultStatus": result_status,
            "stats": stats,
        }

    else:

        print("EXECUTION FAILED")
        error_msg = execution_result.get("error")
        if error_msg:
            print(f"Error: {error_msg}")

        final_result = {
            "executionId": execution_id,
            "resultStatus": "FAIL",
            "error": error_msg,
        }

    return final_result


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    result = main()

    if result.get("resultStatus") == "FAIL":
        raise SystemExit(1)
