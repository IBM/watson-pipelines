#  IBM Confidential
#  OCO Source Materials
#  5737-B37, 5737-C49, 5737-H76
#  (C) Copyright IBM Corp. 2024 All Rights Reserved.
#  The source code for this program is not published or
#  otherwise divested of its trade secrets, irrespective of
#  what has been deposited with the U.S. Copyright Office.

# Usage:
#   python migrate_secrets.py --host https://<cpd-instance-url> -n <cpd-project-name> --user-name <admin-user-name> --user-id <admin-user-id>
#
# Example:
#   python migrate_secrets.py --host https://cpd-cpd-instance.apps.wp485hotfix.cp.fyre.ibm.com -n cpd-instance --user-name cpadmin --user-id 1000331001

import os
import re
import json
import base64
import shutil
import pathlib
import argparse
import subprocess
import socketserver
import requests
from requests.adapters import HTTPAdapter
import urllib3
from datetime import datetime
import time
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


PIPELINES_DIR = "pipelines"
PROJECTS_DIR = "projects"
CPD_INSTANCE = "cpd-instance"
CPD_ADMIN_ID = "1000331001"
CPD_ADMIN_NAME = "cpadmin"
CREDENTIALS_DIR = "creds"

session = requests.Session()
retry = urllib3.Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.verify = False

all_affected = {}
flows = {}
assets_to_primary = {}
primary_to_creds = {}
primary_to_plan = {}

def get_user_token(args, user_id, username):
    params = {
      'uid': user_id,
      'username': username
    }
    response = session.get(
        f"{args.host}/zen-data/internal/v1/service_token",
        headers={'Secret': args.service_broker_token},
        params=params
    )
    if response.ok is False:
        raise Exception("Failed to get user token. Reason: {}".format(response.text))
    return response.json()['token']


def get_projects(args, token, bookmark = None):
    params = {"limit": 100}
    if bookmark:
        params.update({"bookmark": bookmark})
    response = session.get(
        f"{args.host}/v2/projects",
        headers={'Authorization': f'Bearer {token}'},
        params=params
    )
    if response.ok is False:
        raise Exception("Failed to get all projects. Reason: {}".format(response.text))
    return response.json()

def get_project_members(args, token, project_id):
    response = session.get(
        f"{args.host}/v2/projects/{project_id}/members",
        headers={'Authorization': f'Bearer {token}'},
        params={}
    )
    if response.ok is False:
        raise Exception("Failed to get project members. Reason: {}".format(response.text))
    return response.json().get('members')

def get_project(args, token):
    response = session.get(
        f"{args.host}/v2/projects/{args.project_id}",
        headers={'Authorization': f'Bearer {token}'},
        params={}
    )
    if response.ok is False:
        raise Exception("Failed to get project. Reason: {}".format(response.text))
    return response.json()


def get_all_projects(args, token):
    projects = []
    bookmark = None
    while True:
        if bookmark:
            response = get_projects(args, token, bookmark=bookmark)
        else:
            response = get_projects(args, token)
        # bookmark = response.get("bookmark")
        bookmark=None
        for pip in response.get('resources', []):
            projects.append(pip)
        if bookmark is None:
            break
    return projects


def get_user_credentials(args, project_id, asset_id, token, next_page = None):
    url = f"{args.host}/v1/task_credentials"
    if next_page is not None:
        url = next_page
    params = {"type": "parameters"}
    if asset_id is not None:
        params['scope.asset_id'] = asset_id
    if project_id is not None:
        params['scope.project_id'] = project_id

    response = session.get(
        url,
        headers={'Authorization': f'Bearer {token}'},
        params=params
    )
    if response.ok is False:
        raise Exception("Failed to get user credentials. Reason: {}".format(response.text))
    return response.json()


def get_all_user_credentials(args, project_id, asset_id, token = None):
    credentials = []
    next_page_token = None
    if token is None:
        token = args.user_token

    while True:
        response = get_user_credentials(args, project_id, asset_id, token, next_page=next_page_token)
        next_page_token = response.get("next", {}).get('href')
        for pip in response.get('credentials', []):
            credentials.append(pip)
        if next_page_token is None:
            break
    return credentials


def get_credentials_by_id(args, id, token):
    url = f"{args.host}/v1/task_credentials/{id}"
    response = session.get(
        url,
        headers={'Authorization': f'Bearer {token}'}
    )
    if response.ok is False:
        raise Exception("Failed to get credentials with ID: {}. Reason: {}".format(id, response.text))
    return response.json()


def get_secret(args, id, token):
    url = f"{args.host}/v1/task_credentials/{id}/secret"
    response = session.get(
        url,
        headers={'Authorization': f'Bearer {token}'}
    )
    if response.ok is False:
        raise Exception("Failed to get user secret. Reason: {}".format(response.text))
    return response.json()


def create_credentials(args, project_id, asset_id, name, secret, token):
    url = f"{args.host}/v1/task_credentials"
    scope = {'asset_id': asset_id}
    if project_id is not None:
        scope['project_id'] = project_id

    credentials = {
      'name': name,
      'type': 'parameters',
      'scope': scope,
      'secret': secret
    }
    response = session.post(
        url,
        headers={'Authorization': f'Bearer {token}'},
        json=credentials
    )
    if response.ok is False:
        raise Exception("Failed to create user credential. Reason: {}".format(response.text))
    return response.json()

def delete_credentials(args, id, token = None):
    url = f"{args.host}/v1/task_credentials/{id}"
    if token is None:
        token = args.user_token
    response = session.delete(
        url,
        headers={'Authorization': f'Bearer {token}'}
    )
    if response.ok is False:
        raise Exception("Failed to delete user secret. Reason: {}".format(response.text))


def get_asset(args, asset_id, token):
    response = session.get(f"{args.host}/v2/assets/{asset_id}",
                            params={'project_id': args.project_id},
                            headers={'Authorization': f'Bearer {token}'}
                            )
    if response.ok is False:
        raise Exception("Failed to get asset. Reason: {}".format(response.text))
    return response.json()


def get_pipelines(args, token, project_id, next_query = None):
    query = {"query": "*:*"}
    if next_query is not None:
        query = next_query
    params = {"project_id": project_id}

    response = session.post(
        f"{args.host}/v2/asset_types/orchestration_flow/search",
        headers={'Authorization': f'Bearer {token}'},
        params=params,
        json=query
    )
    if response.ok is False:
        print("Failed to get all pipelines. Reason: {}".format(response.text))
        return None
    return response.json()


def get_pipeline_flow_json(args, token, project_id, pipeline_id):
    print(f"Get pipeline {pipeline_id} flow json")
    params = {"format": "flow", "version": "any"}
    _url = f"{args.host}/apis/v1/pipelines/{pipeline_id}/templates"
    response = session.get(
        url=_url,
        headers={'Project-ID': project_id, 'Authorization': f'Bearer {token}'},
        params=params
    )
    if response.ok is False:
        print("Failed to get pipeline flow json. Reason: {}".format(response.text))
        return None
    return json.loads(response.json().get("flow"))


def get_all_pipelines(args, token, project_id):
    pipelines = {}
    next = None
    while True:
        response = get_pipelines(args, token, project_id, next_query=next)
        if response is None:
            return pipelines
        next = response.get("next")
        for pip in response.get('results', []):
            pipeline_id = pip.get('metadata').get('asset_id')
            flow = get_pipeline_flow_json(args, token, project_id, pipeline_id)
            if flow is None:
                continue
            flow['name'] = pip.get('metadata').get('name')
            pipelines[pipeline_id] = flow
        if next is None:
            break
    return pipelines


def upload_pipeline_version(args, project_id, pipeline_id, content,
                    name, token, volatile = True):
    params = {"name": name, "pipelineid": f"{pipeline_id}"}
    if volatile:
        params.update({"volatile": 'true'})
    response = session.post(
        f"{args.host}/apis/v1/pipelines/upload_version",
        headers={'Project-ID': project_id, 'Authorization': f'Bearer {token}'},
        files={'uploadfile': content}, params=params
    )
    if response.ok is False:
        raise Exception("Failed to upload new pipeline version. Reason: {}".format(response.text))
    return response.json()


def upload_pipeline(args, project_id, content,
                    name, token, volatile = True):
    params = {"name": name}
    if volatile:
        params.update({"volatile": 'true'})
    response = session.post(
        f"{args.host}/apis/v1/pipelines/upload",
        headers={'Project-ID': project_id, 'Authorization': f'Bearer {token}'},
        files={'uploadfile': content}, params=params
    )
    if response.ok is False:
        raise Exception("Failed to upload new pipeline. Reason: {}".format(response.text))
    return response.json()


def delete_pipeline(args, project_id, pipeline_id, token):
    _url = f"{args.host}/apis/v1/pipelines/{pipeline_id}"
    response = session.delete(
        url=_url,
        headers={'Project-ID': project_id, 'Authorization': f'Bearer {token}'}
    )
    if response.ok is False:
        raise Exception("Failed to delete pipeline. Reason: {}".format(response.text))


def generate_token(args):
    try:
        payload = {"username": args.username}
        if args.password is not None:
            payload['password'] = args.password
        else:
            payload['api_key'] = args.apikey
        response = requests.post(
            f"{args.host}/icp4d-api/v1/authorize",
            json=payload,
            headers={"cache-control": "no-cache", "content-type": "application/json"},
            verify=False
        )
        token = response.json().get("token")
        if token is None:
            raise Exception
    except:
        common_service_url = str(args.host).replace("cpd-zen", "cp-console")
        response = requests.post(
            f"{common_service_url}/v1/auth/identitytoken",
            headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=f"grant_type=password&username={args.username}&password={args.password}&scope=openid",
            verify=False
        )
        if not response.ok:
            raise Exception(f"Unable to generate IAM access token! Response: {response.text}")
        iam_token = response.json().get("access_token")
        response = requests.get(
            f"{args.host}/v1/preauth/validateAuth",
            headers={"username": args.username, "iam-token": iam_token},
            verify=False
        )
        if not response.ok:
            raise Exception(f"Unable to generate ZEN access token! Response: {response.text}")
        token = response.json().get("accessToken")

    print(f"Access token generated: {token[:10]}...")
    return token


def get_service_broker_token_from_secret(args):
    get_secret_cmd = [args.oc_path, "-n", args.namespace, "get", "secret", "zen-service-broker-secret", "--output", "json"]
    result = subprocess.run(get_secret_cmd, check=True, stdout=subprocess.PIPE)
    service_secret = json.loads(result.stdout)
    token_encoded = service_secret.get("data", {}).get("token", None)
    if token_encoded is None:
        raise Exception("Invalid `zen-service-broker-secret` secret: {}".format(service_secret))
    return base64.b64decode(token_encoded)


def get_couchdb_credentials_from_secret(args):
    get_secret_cmd = [args.oc_path, "-n", args.namespace, "get", "secret", "wdp-couchdb", "--output", "json"]
    result = subprocess.run(get_secret_cmd, check=True, stdout=subprocess.PIPE)
    service_secret = json.loads(result.stdout)
    adminPassword64 = service_secret.get("data", {}).get("adminPassword", None)
    adminUsername64 = service_secret.get("data", {}).get("adminUsername", None)
    if adminUsername64 is None or adminPassword64 is None:
        raise Exception("Invalid `wdp-couchdb` secret: {}".format(service_secret))
    adminPassword = base64.b64decode(adminPassword64).decode('utf-8')
    adminUsername = base64.b64decode(adminUsername64).decode('utf-8')
    adminAndPassword = f"{adminUsername}:{adminPassword}"
    print(f"CouchDB adminUsername={adminUsername}")
    return base64.b64encode(adminAndPassword.encode('utf-8')).decode("utf-8")


def get_free_port_for_proxy():
    with socketserver.TCPServer(("127.0.0.1", 0), None) as s:
        return s.server_address[1]

def forward_couchdb_port(args):
    port_forward_cmd = [
        f"while true; do {args.oc_path} -n {args.namespace} port-forward service/wdp-couchdb-svc --pod-running-timeout=4h --address '0.0.0.0' {args.couchdb_proxy_port}:6984; done",
    ]
    print(f"Starting CouchDB proxy: {port_forward_cmd}")
    return subprocess.Popen(port_forward_cmd, shell=True)


def get_couchdb_url_from_secret(args, namespace):
    get_secret_cmd = [args.oc_path, "-n", namespace, "get", "secret", "couchdb-url", "--output", "json"]
    result = subprocess.run(get_secret_cmd, check=True, stdout=subprocess.PIPE)
    service_secret = json.loads(result.stdout)
    adminPassword = service_secret.get("data", {}).get("adminPassword", None)
    adminUsername = service_secret.get("data", {}).get("adminUsername", None)
    if adminUsername is None or adminPassword:
        raise Exception("Invalid `wdp-couchdb` secret: {}".format(service_secret))
    return base64.b64decode(f"{adminUsername}:{adminPassword}")


def patch_credentials_scope(args, credential_id, project_id):
    url = f"https://127.0.0.1:{args.couchdb_proxy_port}/task-credentials/{credential_id}"
    print(f"Using CouchDB proxy URL: {url}")
    response = session.get(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'}
    )
    if response.ok is False:
        raise Exception("Failed to get user credential. Reason: {}".format(response.text))
    credential = response.json()
    credential['scope']['project_id'] = project_id
    response = session.put(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'},
        json=credential
    )
    if response.ok is False:
        raise Exception("Failed to put user credential. Reason: {}".format(response.text))
    return response.json()
 
def get_credentials_for_asset(args, asset_id):
    url = f"https://127.0.0.1:{args.couchdb_proxy_port}/task-credentials/_find"
    query={
      "selector": {
        "$and": [
          {
            "scope.job_id": {
              "$exists": False
            }
          },
          {
            "scope.asset_id": asset_id
          }
        ]
      },
      "limit": 3000
    }
    response = session.post(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'},
        json=query
    )
    if response.ok is False:
        raise Exception("Failed to put get credential. Reason: {}".format(response.text))
    return response.json()["docs"]

def prepare_migration_secret(args, token):
    fixed_asset_id = 'migration_helper'
    url = f"https://127.0.0.1:{args.couchdb_proxy_port}/task-credentials/_find"
    query={
      "selector": {
        "scope.asset_id": fixed_asset_id
      }
    }
    response = session.post(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'},
        json=query
    )
    if response.ok is False:
        raise Exception("Failed to check helper credentials. Reason: {}".format(response.text))
    found = response.json()["docs"]
    if len(found) > 0:
        return found[0]["secret_id"] 
    
    url = f"{args.host}/v1/task_credentials"
    payload = {
    "name": fixed_asset_id,
    "type": "parameters",
    "secret":{},
    "scope": {"asset_id": fixed_asset_id}
    }

    response = session.post(
        url,
        headers={'Authorization': f'Bearer {token}'},
        json=payload
    )
    if response.ok is False:
        raise Exception("Failed to get create helper credentials. Reason: {}".format(response.text))
    return prepare_migration_secret(args)

def prepare_fixed_secret(args, token, migration_helper_secret, asset_id, project_id, secret):
    current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    secret_urn = prepare_empty_secret(args, token)
    data = {
      "created_at": current_timestamp,
      "creator_id": "",
      "name": "orchestration_flow_parameters_migrated",
      "owner": {
        "user_id": args.user_name
      },
      "scope": {
        "asset_id": asset_id,
        "project_id": project_id
      },
      "secret_id": secret_urn,
      "type": "parameters",
      "updated_at": current_timestamp
    }
    fixed_asset_id = 'migration_helper'
    url = f"https://127.0.0.1:{args.couchdb_proxy_port}/task-credentials"
    response = session.post(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'},
        json=data
    )
    if response.ok is False:
        return "failure : could not create base record. Reason: {}".format(response.text)
    new_id = response.json()["id"]

    print(f"created record for asset {asset_id} and project {project_id}: {new_id}")

    if len(secret) == 0:
        return "success"

    url = f"{args.host}/v1/task_credentials/{new_id}"
    payload = [{
        "op":"replace",
        "path":"/secret",
        "value": secret
    }]

    response = session.patch(
        url,
        headers={'Authorization': f'Bearer {token}'},
        json=payload
    )
    if response.ok is False:
        return "failure: could not patch the record. Reason: {}".format(response.text)
    print(f"record ${new_id} patched : {response.json()}")
    return "success"

def extract_secret_payload(args, flow):
    if "pipelines" not in flow:
        return {}
    if len(flow["pipelines"]) == 0:
        return {}        
    if "pipeline_data" not in flow["pipelines"][0]["app_data"]:
        return {}
    if "inputs" not in flow["pipelines"][0]["app_data"]["pipeline_data"]:
        return {}   
    inputs=flow["pipelines"][0]["app_data"]["pipeline_data"]["inputs"]
    payload={}
    for inp in inputs:
        if "default" in inp and isinstance(inp["default"], str) and "{encval}" in inp["default"]:
            payload[inp["name"]]=inp["default"]
    return payload

def is_scope_set_in_latest_creds(args, project_id, asset_id, token):
    response = get_user_credentials(args, project_id, asset_id, token, next_page = None)
    creds=response["credentials"]
    print(creds, len(creds))
    if len(creds) > 0:
        last = creds[0]
        return "project_id" not in last["scope"]
    return false    

def prepare_fix_plan(args, affected, creds):
    ppid = affected["primary_pipeline_id"]
    actions = []
    if affected["hasSecref"]:
        actions.append({
            "action":"break",
            "reason":"cannot be fixed now as it contains refenences to secrets"
        })
        return actions
    if not affected["hasEncval"] and not affected["hasSecref"]: 
        actions.append({
            "action":"break",
            "reason":"nothing to fix"
        })
        return actions    
    if not affected["hasSecref"]:
        fixed = []   
        for c in creds:
            cid = c["_id"]
            if "project_id" in c["scope"]:
                actions.append({
                    "action":"skip",
                    "reason":f"ignore scoped record: {cid}",
                    "record": c
                })
                fixed.append(c["scope"]["project_id"])
            else:
                actions.append({
                    "action":"disable",
                    "reason":f"disabel unscoped record {cid}",
                    "record": c
                })
        projects =  affected["projects"]  
        for p in projects:
            if p not in fixed:
                actions.append({
                    "action":"create",
                    "reason":f"create record for asset {ppid} and project {p}",
                    "asset_id": ppid,
                    "project_id": p
                })
                fixed.append(p)
                    
    return actions  

def disable_credentials_record(args, record):
    credential_id = record["_id"]
    url = f"https://127.0.0.1:{args.couchdb_proxy_port}/task-credentials/{credential_id}"

    record['scope']['project_id'] = "00000000-0000-0000-0000-000000000000"
    response = session.put(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'},
        json=record
    )
    if response.ok is False:
        return "failure: {}".format(response.text)
    return "success"

def execute_disable_action(args, action, admin_token):
    record = action["record"]
    return disable_credentials_record(args, record)

def execute_create_action(args, action, admin_token, migration_helper_secret):
    asset_id = action["asset_id"]
    project_id = action["project_id"]  
    key = f"{asset_id}_at_{project_id}"
    if key not in flows:
       return f"ignored: {asset_id} is not in the project {project_id}"
    else:
       payload=extract_secret_payload(args, flows[key])
       print(f"attempt to fix: {asset_id} in project {project_id} : {len(payload)} parameters")
       return prepare_fixed_secret(args, admin_token, migration_helper_secret, asset_id, project_id, payload)   

def execute_plan(args, affected, actions, admin_token, migration_helper_secret):
    for a in actions: 
        action = a["action"]
        reason = a["reason"]
        if action == "disable":
            print(f"execute disable action")
            rsp = execute_disable_action(args, a, admin_token)   
            print(f"execute disable action completed with status {rsp}")
        if action == "create":
            print(f"execute create action")
            rsp = execute_create_action(args, a, admin_token, migration_helper_secret)  
            print(f"execute create action completed with status {rsp}")              

def prepare_empty_secret(args, token):
    print("attempt to create empty secret")
    url = f"{args.host}/zen-data/v2/secrets"
    payload = {
        "secret_name":f"migration-helper-{datetime.now().strftime('%s-%f')}",
        "type":"generic",
        "vault_urn": "0000000000:internal",
        "secret": {
            "generic": {
                "task_credentials_empty_secret_param": "placeholder"
            }
        }
    }

    response = session.post(
        url,
        headers={'Authorization': f'Bearer {token}'},
        json=payload
    )
    if response.ok is False:
        raise Exception("Could not create empty secret. Reason: {}".format(response.text))
        return ""
    secret_urn = response.json()["secret_urn"]
    print(f"secret {secret_urn} created : {response.json()}")
    return secret_urn   

def get_all_pipeline_secrets(args):
    url = f"https://127.0.0.1:{args.couchdb_proxy_port}/task-credentials/_find"
    query={
      "selector": {
        "$and": [
          {
            "scope.job_id": {
              "$exists": False
            }
          },
          {
            "type": "parameters"
          }
        ]
      },
      "limit": 5000
    }
    response = session.post(
        url,
        headers={'Authorization': f'Basic {args.couchdb_credentials}'},
        json=query
    )
    if response.ok is False:
        print("Failed to get credentials. Reason: {}".format(response.text))
        raise Exception("Failed to get credentials. Reason: {}".format(response.text))
    return response.json()["docs"]  

def cred_timestamp(cred):
    if "updated_at" in cred:
        return cred["updated_at"]
    return cred["created_at"]

def get_secret(secret_id, token):
    print("attempt to get secret")
    url = f"{args.host}/zen-data/v2/secrets/{secret_id}"

    response = session.get(
        url,
        headers={'Authorization': f'Bearer {token}'},
    )
    if response.ok is False:
        print("Could not read secret {}. Reason: {}".format(secret_id, response.text))
        return None
    if not "data" in response.json() or not "secret" in response.json()["data"] or not "generic" in response.json()["data"]["secret"]:
        print("Could not read secret {}. Unexpected format: {}".format(secret_id, response.response.json()))
        return None
    return response.json()["data"]["secret"]["generic"]     


def run_migration(args):
    admin_token = args.user_token
    pathlib.Path(f"{CREDENTIALS_DIR}").mkdir(parents=True, exist_ok=True)


    if args.project_id is None:
        projects = get_all_projects(args, admin_token)
    else:
        projects = get_project(args, admin_token)


    project_guids = set()    
    for project in projects:
        project_id = project.get('metadata').get('guid')
        project_name = project.get('entity').get('name')
        project_guids.add(project_id)
        print(f"found project {project_id} : {project_name}")

    print(f"\nList of projects: {project_guids}\n")    

    creds_per_asset = {}
    unscoped_ids = set()
    creds = get_all_pipeline_secrets(args)
    for cred in creds:
        asset_id = cred["scope"]["asset_id"]
        project_id = cred["scope"].get("project_id")
        creds_list = cred.get(asset_id)
        if asset_id in creds_per_asset:
            creds_per_asset[asset_id].append(cred)
        else:
            creds_per_asset[asset_id] = [cred]
            
        if project_id is None:     
            unscoped_ids.add(asset_id) 

    print(f"\nfound {len(creds_per_asset)} individual primary_pipeline_ids")
    for ppid in list(creds_per_asset.keys()):
        if ppid not in unscoped_ids:
            del(creds_per_asset[ppid])
    print(f"\nunscoped found: {len(creds_per_asset)}\n")

    iter = 1
    for ppid, lst in creds_per_asset.items():
        refernced_projects = set()
        for lc in lst:
            if "project_id" in lc["scope"]:
                refernced_projects.add(lc["scope"]["project_id"])
        print(f"------- {iter}/{len(creds_per_asset)} dump for {ppid} refernced projects: {refernced_projects} ------")
        iter+=1
        lst.sort(key=cred_timestamp, reverse=True)
        master = None
        for lc in lst:
            if "project_id" in lc["scope"]:
                refernced_projects.add(lc["scope"]["project_id"])
            if master is None and "project_id" not in lc["scope"]:
                master = lc
            print(f"---> {lc}")     
        print("master:",  master.get("_id"))

        secret_id = master["secret_id"]
        owner_name = master["owner"]["user_id"]
        owener_id = secret_id.split(":")[0]
        token = get_user_token(args, owener_id, owner_name)
        secret = get_secret(secret_id, token)
        print(f"values: {secret.keys()}")
        print()
            
    print(f"DONE")             

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", "-n", type=str, help="CPD instance name (namespace)")
    parser.add_argument("--user-id", type=str, help="Admin user ID")
    parser.add_argument("--user-name", type=str, help="Admin user name")
    parser.add_argument("--user-token", type=str, help="Admin user token")
    parser.add_argument("--service-broker-token", type=str, help="Service Broker token")
    parser.add_argument("--couchdb-credentials", type=str, help="CouchDB credentials in base64 format")
    parser.add_argument("--couchdb-proxy-port", type=str, help="CouchDB proxy local port number")
    parser.add_argument("--project-id", type=str, help="project-id")
    parser.add_argument("--primary-pipeline-id", type=str, help="primary-pipeline-id")
    parser.add_argument("--fix", action='store_true')
    parser.add_argument("--pipeline-id", type=str, help="pipeline-id")
    parser.add_argument("--host", type=str, help="Cluster host")
    parser.add_argument("--oc-path", type=str, help="OpenShift Client path")

    args = parser.parse_args()

    if args.host is None:
        print(f"Missing --host parameter. Please provide cluster host.")
        exit(1)
    if args.fix is None:
        print(f"Missing --fix. Using default: false.")
        args.fix = False
    if args.host.endswith('/'):
        args.host = args.host[:-1]   
    if args.namespace is None:
        print(f"Missing --namespace parameter. Using default: {CPD_INSTANCE}.")
        args.namespace = CPD_INSTANCE
    if args.oc_path is None:
        args.oc_path = shutil.which("oc")
        print(f"Using oc path: {args.oc_path}")
    if args.user_id is None:
        print(f"Missing --user-id parameter. Using default: {CPD_ADMIN_ID}.")
        args.user_id = CPD_ADMIN_ID
    if args.user_name is None:
        print(f"Missing --user-name parameter. Using default: {CPD_ADMIN_NAME}.")
        args.user_name = CPD_ADMIN_NAME
    if args.service_broker_token is None:
        print(f"Getting Service Broker token from secret...")
        args.service_broker_token = get_service_broker_token_from_secret(args)
    if args.user_token is None:
        args.user_token = get_user_token(args, args.user_id, args.user_name)
    if args.couchdb_credentials is None:
        print(f"Getting CouchDB credentials token from secret...")
        args.couchdb_credentials = get_couchdb_credentials_from_secret(args)
    if args.couchdb_proxy_port is None:
        print(f"Getting CouchDB proxy port...")
        args.couchdb_proxy_port = get_free_port_for_proxy()

    print("fix flag is set to:", args.fix)
    print("primary_pipeline_id is set to:", args.primary_pipeline_id) 

    with forward_couchdb_port(args) as proxy_proc:
        run_migration(args)
        proxy_proc.terminate()

