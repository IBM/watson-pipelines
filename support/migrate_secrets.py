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
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


PIPELINES_DIR = "pipelines"
CPD_INSTANCE = "cpd-instance"
CPD_ADMIN_ID = "1000331001"
CPD_ADMIN_NAME = "cpadmin"

session = requests.Session()
retry = urllib3.Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.verify = False


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


def run_migration(args):
    admin_token = args.user_token
    pathlib.Path(PIPELINES_DIR).mkdir(parents=True, exist_ok=True)

    if args.project_id is None:
        projects = get_all_projects(args, admin_token)
    else:
        projects = [get_project(args, admin_token)]

    for project in projects:
        project_id = project.get('metadata').get('guid')

        if project.get('entity').get('storage').get('type') == 'local_git_storage':
            print(f"Skipping git based project {project_id}")
            continue

        print(f"Processing project {project_id}")
        pipelines = get_all_pipelines(args, admin_token, project_id)
        if pipelines == {}:
            continue
        for asset_id, flow in pipelines.items():
            with open(f"{PIPELINES_DIR}/{asset_id}.json", "w") as f:
                f.write(json.dumps(flow, indent=2))
        primary_pipelines = {flow['primary_pipeline']: asset_id for asset_id, flow in pipelines.items()}
        members = get_project_members(args, admin_token, project_id)
        credentials = get_all_user_credentials(args, project_id, None, admin_token)
        print("\tCredentials:")
        for c in credentials:
            print(f"\t{c}")
        for member in members:
            uid = member.get('id')
            username = member.get("user_name")
            print(f"\tProcessing member {uid}: {username}")
            user_token = get_user_token(args, uid, username)
            for credential in credentials:
                owner = credential.get('owner', {})
                if owner['user_id'] == username:
                    scope = credential.get('scope', {})
                    id = credential.get('id')
                    name = credential.get('name')
                    secret = get_secret(args, id, user_token)
                    primary_pipeline = scope.get('asset_id')
                    asset_id = primary_pipelines.get(primary_pipeline)
                    if asset_id is not None:
                      print(f"\t\tProcessing credential {credential}")
                      print(f"\t\tSecret {id}: {secret}")

                      if 'project_id' not in scope:
                        patch_response = patch_credentials_scope(args, id, project_id)
                        patched_credentials = get_credentials_by_id(args, id, user_token)
                        print(f"\t\tPatched credentials {id}: {patched_credentials}")
                      else:
                        print("\t\tProject scope already set")
                    else:
                      print("\t\tPipeline with primary ID {} not found".format(primary_pipeline))

    print("Done processing all projects")


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
    parser.add_argument("--host", type=str, help="Cluster host")
    parser.add_argument("--oc-path", type=str, help="OpenShift Client path")

    args = parser.parse_args()

    if args.host is None:
        print(f"Missing --host parameter. Please provide cluster host.")
        exit(1)
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

    with forward_couchdb_port(args) as proxy_proc:
        run_migration(args)
        proxy_proc.terminate()
