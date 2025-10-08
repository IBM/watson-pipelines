"""
The script updates the 'sender' parameter in send-email nodes.

Scenarios:

1. Project-Wide Update

   Updates the sender parameter across all pipelines in the specified project.

   Required arguments:
     --host           URL of the server or service
     --username       Authentication username
     --password       Authentication password
     --project-name   Name of the project to update
     --sender-value   New value to set for the 'sender' parameter

   Example:
     python update_sender.py project \
         --host https://cpd-cpd-instance.cp.fyre.ibm.com \
         --username admin \
         --password secret \
         --project-name MyProject \
         --sender-value $Ev_EMAIL_SENDERS_LIST

2. Single Pipeline Update

   Updates the sender parameter in a specific pipeline within the project.

   Required arguments:
     --host           URL of the server or service
     --username       Authentication username
     --password       Authentication password
     --project-name   Name of the project
     --pipeline-name  Name of the specific pipeline to update
     --sender-value   New value to set for the 'sender' parameter

   Example:
     python update_sender.py pipeline \
         --host https://cpd-cpd-instance.cp.fyre.ibm.com \
         --username admin \
         --password secret \
         --project-name MyProject \
         --pipeline-name PipelineA \
         --sender-value sender_param_name
"""
import os
import sys
import json
import logging
import argparse
import subprocess
import tempfile
from typing import Dict, List, Any, Union

JSONType = Union[Dict[str, Any], List[Any]]

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

_env = os.environ.copy()


def add_common_args(p: argparse.ArgumentParser):
    p.add_argument("--host", required=True, help="Server or service host URL.")
    p.add_argument("--username", required=True, help="Authentication username.")
    p.add_argument("--password", required=True, help="Authentication password.")
    p.add_argument("--project-name", required=True, help="Name of the project.")
    p.add_argument("--sender-value", required=True, help="New sender parameter value.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update 'sender' parameter in Notification activities in pipelines."
    )

    subparsers = parser.add_subparsers(
        title="Scenarios", dest="scenario", required=True,
        help="Choose between project-wide or single-pipeline update."
    )

    project_parser = subparsers.add_parser(
        "project", help="Update all pipelines in the specified project."
    )
    add_common_args(project_parser)

    pipeline_parser = subparsers.add_parser(
        "pipeline", help="Update a specific pipeline in the project."
    )
    pipeline_parser.add_argument(
        "--pipeline-name", required=True, help="Name of the specific pipeline to update."
    )
    add_common_args(pipeline_parser)

    return parser.parse_args()


def cpdctl_exec(_args: list[str]) -> bytes:
    p = subprocess.Popen(
        args=_args,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env
    )

    stdout, stderr = p.communicate()

    if p.returncode != 0:
        logger.error(stderr.decode())
        raise subprocess.CalledProcessError(p.returncode, ' '.join(p.args), stderr=stderr.decode())

    return stdout


def config_cpdctl(host: str, username: str, password: str):
    global _env
    _tmp_config_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
    _tmp_config_file.write("users:\nprofiles:")
    _tmp_config_file.flush()
    _tmp_config_file.close()
    _env["CPD_CONFIG"] = _tmp_config_file.name

    _args = [
        "cpdctl", "config", "profile",
        "set", "TMPPROFILE",
        "--url", host,
        "--username", username,
        "--password", password
    ]

    _ = cpdctl_exec(_args)

    return _tmp_config_file.name


def get_pipeline_template(project_id: str, pipeline_id: str) -> JSONType:
    p1 = subprocess.Popen(
        args=["cpdctl", "pipeline", "get-template",
              "--project-id", project_id,
              "--pipeline-id", pipeline_id,
              "--version", "any",
              "--format", "flow", "--output", "json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env
    )
    p2 = subprocess.Popen(
        args=["jq", ".flow", "-r"],
        stdin=p1.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env
    )

    p1.stdout.close()
    _, p1_stderr = p1.communicate()
    stdout, stderr = p2.communicate()

    if p1.returncode != 0:
        raise subprocess.CalledProcessError(p1.returncode, ' '.join(p1.args), stderr=p1_stderr.decode())

    if p2.returncode != 0:
        raise subprocess.CalledProcessError(p2.returncode, ' '.join(p2.args), stderr=stderr.decode())

    result = json.loads(stdout)
    return result


def get_pipeline_ids(project_id: str, pipeline_name: str | None = None) -> List[dict]:
    pipelines = []
    page_token = None
    page_size = 100

    while True:
        _args = [
            "cpdctl", "pipeline", "list",
            "--project-id", project_id,
            "--page-size", str(page_size),
            "--output", "json"
            ]
        if page_token:
            _args.extend([
                "--page-token", page_token
            ])

        result = json.loads(cpdctl_exec(_args))

        pipelines.extend(result.get("pipelines", []))
        page_token = result.get("next_page_token")

        if not page_token:
            break

    if pipeline_name is None:
        return pipelines
    else:
        return [item for item in pipelines if item.get("name") == pipeline_name]


def get_project_id(project_name: str) -> str | None:
    _args = [
        "cpdctl", "project", "list",
        "-n", project_name,
        "--output", "json"
    ]

    result = json.loads(cpdctl_exec(_args))

    if result.get("total_results") == 0:
        return None
    else:
        return result["resources"][0]["metadata"]["guid"]


def parse_expression(new_sender_value: str, flow: JSONType) -> str:

    _app_data = flow.get("app_data", {})
    _pipeline_data = _app_data.get("pipeline_data", {})
    _user_variables = [var["name"] for var in _pipeline_data.get("variables", [])]
    _parameter_sets = [param["name"] for param in _pipeline_data.get("parameter_sets", [])]

    _primary_pipeline_id = flow.get("primary_pipeline", "")
    _pipelines = flow.get("pipelines", [])
    _primary_pipeline = next((d for d in _pipelines if d["id"] == _primary_pipeline_id), {})
    _primary_pipeline_app_data = _primary_pipeline.get("app_data", {})
    _primary_pipeline_pipeline_data = _primary_pipeline_app_data.get("pipeline_data", {})
    _pipeline_params = [p["name"] for p in _primary_pipeline_pipeline_data.get("inputs", [])]

    if "." in new_sender_value and new_sender_value.split(".", 1)[0] in _parameter_sets:
        _split = new_sender_value.split(".", 1)
        return f"param_sets.{_split[0]}[\"{_split[1]}\"]"
    elif new_sender_value in _user_variables:
        return f"vars.{new_sender_value}"
    elif new_sender_value in _pipeline_params:
        return f"params[\"{new_sender_value}\"]"
    else:
        raise ValueError(f"{new_sender_value} not found in pipeline flow")


def process_flow(flow: JSONType, new_sender_value: str) -> bool:
    _value_from_data = {
        "expression": parse_expression(new_sender_value, flow)
    }
    _is_send_email_node = False

    _pipelines = flow.get("pipelines", [])
    for _pipeline in _pipelines:
        _nodes = _pipeline.get("nodes", [])
        for _node in _nodes:
            _app_data = _node.get("app_data", {})
            _component_type = _app_data.get("componentLabelRef")
            if _component_type == "Send email":
                _is_send_email_node = True
                _pipeline_data = _app_data.get("pipeline_data", {})
                _inputs = _pipeline_data.get("inputs", [])
                for _input in _inputs:
                    if _input.get("name") == "sender_addr":
                        _input.pop("value", None)
                        _input.pop("ui_data", None)
                        _input["value_from"] = _value_from_data
                        break

    return _is_send_email_node


def update_flow(new_flow: JSONType, project_id: str, pipeline_id: str) -> None:

    _tmp_file_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as tmp_file:
            json.dump(new_flow, tmp_file, indent=2)
            _tmp_file_path = tmp_file.name

        _args = [
            "cpdctl", "pipeline", "version", "upload",
            "--file", _tmp_file_path,
            "--project-id", project_id,
            "--pipeline-id", pipeline_id,
            "--volatile", "true"
        ]

        _ = cpdctl_exec(_args)

    finally:
        if _tmp_file_path and os.path.exists(_tmp_file_path):
            os.remove(_tmp_file_path)


if __name__ == "__main__":
    args = parse_args()

    _config_file_path: str | None = None

    if args.scenario == "project" or args.scenario == "pipeline":
        try:
            _config_file_path = config_cpdctl(args.host, args.username, args.password)
            project_id = get_project_id(args.project_name)

            pipeline_name = None
            if args.scenario == "pipeline":
                pipeline_name = args.pipeline_name

            pipelines_to_process = get_pipeline_ids(project_id, pipeline_name)

            for pipeline in pipelines_to_process:
                try:
                    logger.info(f"Processing pipeline: {pipeline.get('name')}, id: {pipeline.get('id')}")
                    _flow = get_pipeline_template(project_id, pipeline.get("id"))
                    is_send_email_node = process_flow(_flow, args.sender_value)
                    if is_send_email_node:
                        update_flow(_flow, project_id, pipeline.get("id"))
                except subprocess.CalledProcessError as e:
                    logger.error("Command '%s' failed with return code %d.\nOutput:\n%s",
                                 e.cmd, e.returncode, e.stderr)

        except Exception as e:
            logger.exception("Unexpected error: %s", e)

        finally:
            if _config_file_path or os.path.exists(_config_file_path):
                os.remove(_config_file_path)
    else:
        logger.error("Invalid scenario selected.")
        sys.exit(1)
