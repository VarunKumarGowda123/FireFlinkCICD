import json
import requests
import re
import copy
import time
import os
from dotenv import load_dotenv
load_dotenv()  

#Usable Machine List
usable_machines = json.loads(os.getenv("usable_machines"))
#time setting
interval_seconds = int(os.getenv("interval_seconds"))
timeout_seconds = int(os.getenv("timeout_seconds"))
# Generated Curl
file_path = os.getenv("CURL_FILE")
curl_str = open(file_path).read()

# Function to fetch Data from the given Curl, Returns a dictionary of parsed data

def parse_curl(curl_str):

    url_match = re.search(r"curl\s+--location\s+'([^\"]+)'", curl_str)
    url = url_match.group(1) if url_match else None

    json_match = re.search(r'--data-raw\s+"({[\s\S]*?})"', curl_str)

    if not json_match:
        raise ValueError("JSON not found in curl command")

    json_str = json_match.group(1)
    json_str = json_str.encode("utf-8").decode("unicode_escape")

    try:
        data = json.loads(json_str)
    except ValueError:
        raise SystemExit("Failed to parse CURL command") 

    return {
        "url": url,
        # "json": data,
        "projectId": data.get("projectId"),
        "accessToken": data.get("accessToken"),
        "licenseId": data.get("licenseId"),
        "suiteId": data.get("suiteId"),
        "waitConfig": data.get("waitConfig")
    }

parsed_data = parse_curl(curl_str)

#Function to get Machine ID and instances with each machine
def fetch_selected_machines(suiteId, accessToken, projectId):
    url = f"https://test3.fireflink.com/project/optimize/v3/suites/{suiteId}"

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
        "authorization": f"Bearer {accessToken}",
        "projectid": projectId,
        "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

    # Cookies (static example — can be parameterized if needed)
    cookies = {
        "_ga": "GA1.1.199505569.1706088261",
        "_clck": "omdtlb^2^g1d^0^1785",
        "licenseType": "C-Professional",
        "_ga_MYGNRDJ84W": "GS2.1.s1764246620$o128$g1$t1764246659$j21$l0$h890122976",
    }

    response = requests.get(url, headers=headers, cookies=cookies)
    print("Status Code:", response.status_code)

    # Handle status code errors BEFORE JSON parsing
    if response.status_code == 401:
        raise SystemExit("401 Unauthorized — Invalid or expired access token. Regenerate the Curl \n")

    elif response.status_code == 403:
        raise SystemExit("403 Forbidden — You don't have permission")

    elif response.status_code == 404:
        raise SystemExit(f"404 Not Found — URL not found: {url}")

    elif response.status_code >= 500:
        raise SystemExit("Server error — Try again later")

    elif response.status_code != 200:
        raise SystemExit(f"Unexpected status code {response.status_code}")


    raw = response.text
    try:
        data = json.loads(raw)
    except ValueError:
        raise SystemExit("Failed to parse JSON response") 
            

    machines = data['responseObject']['executionSettings']['machines']['selectedMachines']

    # Extract selected machines + instance mapping
    selected_ids = []
    machine_instances = []

    for m in machines:
        selected_ids.append(m["clientId"])
        machine_instances.append({
            "clientId": m["clientId"],
            "machineInstances": m["machineInstances"]
        })

    # Return everything cleanly
    return selected_ids,machine_instances

selected_ids, machine_instances = fetch_selected_machines(
    suiteId = parsed_data["suiteId"],
    accessToken = parsed_data["accessToken"],
    projectId = parsed_data["projectId"]
)


def fetch_active_machines(accessToken, licenseId, selected_machines):
    
    url = "http://test3.fireflink.com/project/optimize/v3/client-system-config/machine-status"

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
        "authorization": f"Bearer {accessToken}",
        "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "licenseId": licenseId
    }

    response = requests.get(url, headers=headers)
    status = response.status_code

    # Handle status codes BEFORE JSON parsing
    if status == 401:
        raise SystemExit("401 Unauthorized — Invalid or expired access token, Regenerate Curl")

    elif status == 403:
        raise SystemExit("403 Forbidden — You don't have access")

    elif status == 404:
        raise SystemExit(f"404 Not Found — URL not found: {url}")

    elif status >= 500:
        raise SystemExit("Server error — Try again later")

    elif status != 200:
        raise SystemExit(f"Unexpected status code {status}")
    raw = response.text

    try:
        data = json.loads(raw)
    except ValueError:
        raise SystemExit("Failed to parse JSON response")

    machines = data['responseObject'].get("clientSystems", [])

    available_clientid_list = []
    available_clientid_list_extra = []
    available_machines = []

    for m in machines:
        if m.get("status") == "Active" and m["machine"]["hostName"] in usable_machines:
            entry = {
                "clientId": m["clientId"],
                "status": m["status"],
                "machineInfo": m["machine"]
            }
            available_machines.append(entry)

            if m["clientId"] in selected_machines:
                available_clientid_list.append(m["clientId"])
            else:
                available_clientid_list_extra.append(m["clientId"])

    return available_machines,available_clientid_list,available_clientid_list_extra

available_machines, available_clientid_list, available_clientid_list_extra = fetch_active_machines(
    accessToken = parsed_data["accessToken"],
    licenseId = parsed_data["licenseId"],
    selected_machines = selected_ids
)

def build_machine_headers(
        final_selection_clients,
        header_template,
        instance_selected,
        available_clientid_list,
        replaced_map
    ):
    """
    Builds full machine execution headers for each selected machine.

    Args:
        final_selection_clients (list): list of selected machine objects
        header_template (dict): base template for header duplication
        instance_selected (list): list of {clientId, machineInstances}
        available_clientid_list (list): IDs that were directly available
        replaced_map (dict): maps replacementId -> originalId

    Returns:
        list: header_inclusion (final list of machine execution headers)
    """

    header_inclusion = []

    for client in final_selection_clients:

        header = copy.deepcopy(header_template)
        clientID = client["clientId"]
        machineINFO = client["machineInfo"]

        # 1. If machine is directly available
        if clientID in available_clientid_list:
            machineInstances = next(
                (item["machineInstances"] for item in instance_selected if item["clientId"] == clientID),
                None
            )

        # 2. Machine was replaced → find original clientID from replaced_map
        else:
            original_id = replaced_map.get(clientID)
            machineInstances = next(
                (item["machineInstances"] for item in instance_selected if item["clientId"] == original_id),
                None
            )

        # Update machineInstances with new clientID and machineInfo
        for inst in machineInstances:
            inst["clientId"] = clientID
            inst["machineInfo"] = machineINFO

        # Update header
        header["clientId"] = clientID
        header["machineInstances"] = machineInstances

        header_inclusion.append(header)

    return header_inclusion
def trigger_execution(url_exe, suiteId, waitConfig, licenseId, accessToken, projectId, header_inclusion=None):

    headers_exe = {
        "Content-Type": "application/json"
    }
    if header_inclusion == None:
        payload_exe = {
            "suiteId": suiteId,
            "waitConfig": waitConfig,
            "licenseId": licenseId,
            "accessToken": accessToken,
            "projectId": projectId,
        }
    else : 
        payload_exe = {
            "suiteId": suiteId,
            "waitConfig": waitConfig,
            "licenseId": licenseId,
            "accessToken": accessToken,
            "projectId": projectId,
            "executionSettings": {
                "machines": {
                    "multiple": "",
                    "executionType": "SEQUENTIAL",
                    "selectedMachines": header_inclusion
                }
            }
        }
        

    response = requests.post(url_exe, headers=headers_exe, data=json.dumps(payload_exe))

    try:
        response_json = response.json()
    except:
        response_json = None

    return {
        "status_code": response.status_code,
        "response_json": response_json,
        "raw": response.content
    }

def poll_machine_status_with_timeout(interval_seconds,timeout_seconds,selected_machines):
    start_time = time.time()
    attempts = 0

    while True:
        attempts += 1
        print(f"\n🔄 Polling attempt #{attempts}")

        # Call your existing function
        
        available_machines, available_clientid_list, available_clientid_list_extra  = fetch_active_machines(
            accessToken=parsed_data["accessToken"],
            licenseId=parsed_data["licenseId"],
            selected_machines=selected_machines
        )
        required = selected_machines

        # Condition 1: All required machines are active
        if all(m in available_machines for m in required):
            print("\n✅ All required machines are ACTIVE. Proceeding...")
            return trigger_execution(parsed_data["url"], 
                      parsed_data["suiteId"], 
                      parsed_data["waitConfig"], 
                      parsed_data["licenseId"],
                      parsed_data["accessToken"], 
                      parsed_data["projectId"]) 
        else: 
            final_list,replaced = check_availability(selected_machines,available_machines,available_clientid_list, available_clientid_list_extra,flag=1)
            if final_list == []:
                pass
            else:
                header_inclusion=build_machine_headers(
                final_list,
                header_template,
                machine_instances,
                available_clientid_list,
                replaced  
                )
                return trigger_execution(parsed_data["url"], 
                      parsed_data["suiteId"], 
                      parsed_data["waitConfig"], 
                      parsed_data["licenseId"],
                      parsed_data["accessToken"], 
                      parsed_data["projectId"],
                      header_inclusion
                      )



        # Condition 2: Timeout
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            print("\n⛔ Timeout reached (5 minutes). Machines did not become active.")

            return trigger_execution(parsed_data["url"], 
                      parsed_data["suiteId"], 
                      parsed_data["waitConfig"], 
                      parsed_data["licenseId"],
                      parsed_data["accessToken"], 
                      parsed_data["projectId"])

        # Wait before next poll
        print(f"⏳ Waiting {interval_seconds} seconds before next poll...")
        time.sleep(interval_seconds)

def replace_machines(selected_machines,
                     available_machines,
                     available_clientid_list,
                     available_clientid_list_extra):
    """
    Replace unavailable machines with extra available machines.

    Returns:
        final_selection_clients (list)
        replaced_map (dict)
    """

    final_selection_clients = []
    replaced_map = {}

    for client_id in selected_machines:

        # Case 1: Required machine is available
        if client_id in available_clientid_list:
            index = next(
                (idx for idx, m in enumerate(available_machines) if m["clientId"] == client_id),
                None
            )
            final_selection_clients.append(available_machines[index])
            del available_machines[index]

        # Case 2: Required machine is NOT available → replace
        else:
            if not available_clientid_list_extra:
                raise Exception("❌ No extra machines available for replacement")

            replacement_id = available_clientid_list_extra.pop(0)
            replaced_map[replacement_id] = client_id

            index = next(
                (idx for idx, m in enumerate(available_machines) if m["clientId"] == replacement_id),
                None
            )
            final_selection_clients.append(available_machines[index])
            del available_machines[index]

    return final_selection_clients, replaced_map



def check_availability(selected_machines,
                       available_machines,
                       available_clientid_list,
                       available_clientid_list_extra,
                       flag = None):

    required = len(selected_machines)
    available = len(available_machines)
    final_list = []
    # 1. Not enough active machines at all
    if available < required and flag == None:
        print(poll_machine_status_with_timeout(interval_seconds,timeout_seconds, selected_machines))
        exit(0)
    if available < required  and flag == 1:
        return [] , {}
    
    # 2. If ALL required machines are already active → no replacement needed
    if all(m in available_clientid_list for m in selected_machines):
        final_list = [
            next(m for m in available_machines if m["clientId"] == cid)
            for cid in selected_machines
        ]
        return final_list,{}

    # 3. Replacement required
    final_list, replaced = replace_machines(
        selected_machines,
        available_machines,
        available_clientid_list,
        available_clientid_list_extra
    )

    return final_list,replaced

final_list,replaced = check_availability(selected_ids,
                   available_machines,
                       available_clientid_list,
                       available_clientid_list_extra
)


header_template = {
                    "clientId": "flinko-client-win-04C91941-2E29-42A1-BB35-84F57A170F94",
                    "executionDataSet": {
                        "peVariableSetId": "SUITE_VAR_SETc28c5117-75a0-4046-838f-12ef9965a898",
                        "peVariableSetName": "Variable set from Test dev",
                        "globalVariableSetId": "SUITE_VAR_SETa00bf4f6-c989-4eb2-bc48-65b6f4cb458a",
                        "globalVariableSetName": "Global Variable set from Test dev",
                        "testDataSetId": "TDSa1917181-2baf-4356-ba16-2f0446966ddc",
                        "testDataSetName": "Test DataSet From Test Dev"
                    },
                    "machineInstances": [
                        {
                            "machineInstanceId": "efb174d2-971f-4914-bf7d-3aaa9126b9e9",
                            "numberOfRuns": 1,
                            "clientId": "flinko-client-win-04C91941-2E29-42A1-BB35-84F57A170F94",
                            "executionEnv": "Local",
                            "browserName": "Google Chrome",
                            "browserVersion": "142.0.7444.163",
                            "systemUrl": "TYSS-Bukkapatnam-Sunil",
                            "machineInfo": {
                                "osName": "Windows 11 Pro",
                                "hostName": "TYSS-Bukkapatnam-Sunil",
                                "osVersion": "10.0.26100",
                                "iconName": "windows"
                            },
                            "deviceInfo": [],
                            "headless": False,
                            "runLevelExecutionDataSets": [
                                {
                                    "peVariableSetId": "SUITE_VAR_SETc28c5117-75a0-4046-838f-12ef9965a898",
                                    "peVariableSetName": "Variable set from Test dev",
                                    "globalVariableSetId": "SUITE_VAR_SETa00bf4f6-c989-4eb2-bc48-65b6f4cb458a",
                                    "globalVariableSetName": "Global Variable set from Test dev",
                                    "testDataSetId": "TDSa1917181-2baf-4356-ba16-2f0446966ddc",
                                    "testDataSetName": "Test DataSet From Test Dev",
                                    "runId": "59272c21-64d7-4493-b93c-320cb203c8c4"
                                }
                            ],
                            "instanceId": "",
                            "fireCloudProjectId": "",
                            "fireCloudProjectName": ""
                        },
                        {
                            "machineInstanceId": "efb174d2-971f-4914-bf7d-3aaa9126b9e9",
                            "numberOfRuns": 1,
                            "clientId": "flinko-client-win-04C91941-2E29-42A1-BB35-84F57A170F94",
                            "executionEnv": "Local",
                            "browserName": "Microsoft Edge",
                            "browserVersion": "142.0.3595.80",
                            "systemUrl": "TYSS-Bukkapatnam-Sunil",
                            "machineInfo": {
                                "osName": "Windows 11 Pro",
                                "hostName": "TYSS-Bukkapatnam-Sunil",
                                "osVersion": "10.0.26100",
                                "iconName": "windows"
                            },
                            "deviceInfo": [],
                            "headless": False,
                            "runLevelExecutionDataSets": [
                                {
                                    "peVariableSetId": "SUITE_VAR_SETc28c5117-75a0-4046-838f-12ef9965a898",
                                    "peVariableSetName": "Variable set from Test dev",
                                    "globalVariableSetId": "SUITE_VAR_SETa00bf4f6-c989-4eb2-bc48-65b6f4cb458a",
                                    "globalVariableSetName": "Global Variable set from Test dev",
                                    "testDataSetId": "TDSa1917181-2baf-4356-ba16-2f0446966ddc",
                                    "testDataSetName": "Test DataSet From Test Dev",
                                    "runId": "59272c21-64d7-4493-b93c-320cb203c8c4"
                                }
                            ],
                            "instanceId": "",
                            "fireCloudProjectId": "",
                            "fireCloudProjectName": ""
                        }
                    ]
                }



header_inclusion=build_machine_headers(
        final_list,
        header_template,
        machine_instances,
        available_clientid_list,
        replaced  
)



print(
    trigger_execution(parsed_data["url"], 
                      parsed_data["suiteId"], 
                      parsed_data["waitConfig"], 
                      parsed_data["licenseId"],
                      parsed_data["accessToken"], 
                      parsed_data["projectId"], 
                      header_inclusion)
                      )






def poll_machine_status_with_timeout(interval_seconds,timeout_seconds,selected_machines):
    start_time = time.time()
    attempts = 0

    while True:
        attempts += 1
        print(f"\n🔄 Polling attempt #{attempts}")

        # Call your existing function
        
        available_machines, available_clientid_list, available_clientid_list_extra  = fetch_active_machines(
            accessToken=parsed_data["accessToken"],
            licenseId=parsed_data["licenseId"],
            selected_machines=selected_machines
        )
        required = selected_machines

        # Condition 1: All required machines are active
        if all(m in available_machines for m in required):
            print("\n✅ All required machines are ACTIVE. Proceeding...")
            return 
        else: 
            final_list,replaced = check_availability(selected_machines,available_machines,available_clientid_list, available_clientid_list_extra,flag=1)
            if final_list == []:
                pass
            else:
                header_inclusion=build_machine_headers(
                final_list,
                header_template,
                machine_instances,
                available_clientid_list,
                replaced  
                )
                return trigger_execution(parsed_data["url"], 
                      parsed_data["suiteId"], 
                      parsed_data["waitConfig"], 
                      parsed_data["licenseId"],
                      parsed_data["accessToken"], 
                      parsed_data["projectId"],
                      header_inclusion
                      )



        # Condition 2: Timeout
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            print("\n⛔ Timeout reached (5 minutes). Machines did not become active.")

            return trigger_execution(parsed_data["url"], 
                      parsed_data["suiteId"], 
                      parsed_data["waitConfig"], 
                      parsed_data["licenseId"],
                      parsed_data["accessToken"], 
                      parsed_data["projectId"])

        # Wait before next poll
        print(f"⏳ Waiting {interval_seconds} seconds before next poll...")
        time.sleep(interval_seconds)