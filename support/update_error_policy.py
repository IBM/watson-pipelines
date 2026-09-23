#!/usr/bin/env python3
"""
The script updates the 'error_policy' and/or 'default_error_policy' in Watson Pipelines.

Valid error policy values:
  - fail_on_error      (Pipeline/Node fails on error - default behavior)
  - continue_on_error  (Pipeline/Node continues on error)
  - inherit            (Removes node-level override so it follows pipeline's default_error_policy)

Available Scopes (--scope):
  1. nodes-only         - Updates only individual nodes (WITHOUT changing the pipeline's default policy). [Default]
  2. pipeline-default   - Updates only the pipeline-level default_error_policy (WITHOUT modifying individual nodes).
  3. all                - Updates both the pipeline-level default_error_policy AND all individual nodes.

Scenarios & Examples:

1. Update ONLY nodes (--scope nodes-only)
   - Project-wide (all pipelines):
       python update_error_policy.py project \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --policy continue_on_error \
           --scope nodes-only

   - Single pipeline:
       python update_error_policy.py pipeline \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --pipeline-name "PipelineA" \
           --policy fail_on_error \
           --scope nodes-only

   - Reset nodes to inherit from pipeline default policy:
       python update_error_policy.py project \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --policy inherit \
           --scope nodes-only

2. Update ONLY pipeline default policy (--scope pipeline-default)
   - Project-wide (all pipelines):
       python update_error_policy.py project \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --policy continue_on_error \
           --scope pipeline-default

   - Single pipeline:
       python update_error_policy.py pipeline \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --pipeline-name "PipelineA" \
           --policy fail_on_error \
           --scope pipeline-default

3. Update BOTH pipeline default policy and all nodes (--scope all)
   - Project-wide (all pipelines):
       python update_error_policy.py project \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --policy continue_on_error \
           --scope all

   - Single pipeline:
       python update_error_policy.py pipeline \
           --host https://cpd-instance.example.com \
           --username admin \
           --password secret \
           --project-name MyProject \
           --pipeline-name "PipelineA" \
           --policy fail_on_error \
           --scope all
"""

import os
import sys
import json
import logging
import argparse
import subprocess
import tempfile
from typing import Dict, List, Any, Union, Optional

JSONType = Union[Dict[str, Any], List[Any]]

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

_env = os.environ.copy()

VALID_POLICIES = ["fail_on_error", "continue_on_error", "inherit"]


def add_common_args(p: argparse.ArgumentParser):
    p.add_argument("--host", required=True, help="Server or service host URL.")
    p.add_argument("--username", required=True, help="Authentication username.")
    p.add_argument("--password", required=True, help="Authentication password.")
    p.add_argument("--project-name", required=True, help="Name of the project.")
    p.add_argument(
        "--policy",
        required=True,
        choices=VALID_POLICIES,
        help="Error policy: 'fail_on_error', 'continue_on_error', or 'inherit' (resets node to follow default)."
    )
    p.add_argument(
        "--scope",
        choices=["nodes-only", "pipeline-default", "all"],
        default="nodes-only",
        help="Scope of change: 'nodes-only' (default, leaves pipeline default untouched), 'pipeline-default', or 'all'."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk update 'error_policy' and 'default_error_policy' in Watson Pipelines."
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
        err_msg = stderr.decode().strip()
        logger.error(f"Error executing {' '.join(_args)}: {err_msg}")
        raise subprocess.CalledProcessError(p.returncode, ' '.join(p.args), stderr=err_msg)

    return stdout


def config_cpdctl(host: str, username: str, password: str) -> str:
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


def get_project_id(project_name: str) -> Optional[str]:
    _args = [
        "cpdctl", "project", "list",
        "-n", project_name,
        "--output", "json"
    ]

    result = json.loads(cpdctl_exec(_args))

    if result.get("total_results", 0) == 0 or not result.get("resources"):
        return None
    return result["resources"][0]["metadata"]["guid"]


def get_pipeline_ids(project_id: str, pipeline_name: Optional[str] = None) -> List[dict]:
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
            _args.extend(["--page-token", page_token])

        result = json.loads(cpdctl_exec(_args))
        pipelines.extend(result.get("pipelines", []))
        page_token = result.get("next_page_token")

        if not page_token:
            break

    if pipeline_name is None:
        return pipelines
    else:
        return [item for item in pipelines if item.get("name") == pipeline_name]


def get_pipeline_template(project_id: str, pipeline_id: str) -> dict:
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

    return json.loads(stdout)


def update_flow(new_flow: dict, project_id: str, pipeline_id: str) -> None:
    _tmp_file_path: Optional[str] = None
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


def process_error_policy(
    flow: dict,
    new_policy: str,
    scope: str = "nodes-only"
) -> int:
    """
    Updates the error policy in the flow JSON.
    - scope 'nodes-only': changes nodes without touching pipeline default_error_policy.
    - scope 'pipeline-default': changes only pipeline default_error_policy.
    - scope 'all': changes both pipeline default and all matching nodes.
    - policy 'inherit': removes the explicit node error_policy override so it inherits from default.
    """
    changes_count = 0

    # 1. Update pipeline-level default_error_policy (ONLY if scope is 'all' or 'pipeline-default')
    if scope in ("all", "pipeline-default"):
        if new_policy == "inherit":
            logger.warning("Policy 'inherit' cannot be applied to pipeline-level default_error_policy. Skipping default.")
        else:
            pipeline_data = flow.setdefault("app_data", {}).setdefault("pipeline_data", {})
            old_val = pipeline_data.get("default_error_policy")
            if old_val != new_policy:
                pipeline_data["default_error_policy"] = new_policy
                changes_count += 1
                logger.info(f"  - [Pipeline Default] default_error_policy updated: {old_val} -> {new_policy}")

    # 2. Update node-level error_policy (ONLY if scope is 'all' or 'nodes-only')
    if scope in ("all", "nodes-only"):
        pipelines = flow.get("pipelines", [])
        for sub_pipe in pipelines:
            nodes = sub_pipe.get("nodes", [])
            for node in nodes:
                node_id = node.get("id", "unknown")
                node_app_data = node.setdefault("app_data", {})
                component_type = node_app_data.get("componentLabelRef")

                node_pip_data = node_app_data.setdefault("pipeline_data", {})

                # Case A: Supernodes / Loops with direct error_policy key
                if "error_policy" in node_pip_data:
                    if new_policy == "inherit":
                        del node_pip_data["error_policy"]
                        changes_count += 1
                        logger.info(f"  - [Node {node_id}] Removed error_policy override (now inherits)")
                    elif node_pip_data["error_policy"] != new_policy:
                        node_pip_data["error_policy"] = new_policy
                        changes_count += 1
                        logger.info(f"  - [Node {node_id}] Loop error_policy updated to '{new_policy}'")

                # Case B: Standard nodes via inputs list
                inputs = node_pip_data.setdefault("inputs", [])
                policy_input = next((inp for inp in inputs if inp.get("name") == "error_policy"), None)

                if new_policy == "inherit":
                    # Remove override if present
                    if policy_input is not None:
                        inputs.remove(policy_input)
                        changes_count += 1
                        logger.info(f"  - [Node {node_id}] ({component_type or 'Node'}) Removed error_policy override (now inherits)")
                else:
                    if policy_input is not None:
                        if policy_input.get("value") != new_policy:
                            policy_input["value"] = new_policy
                            policy_input["type"] = "ErrorPolicy"
                            changes_count += 1
                            logger.info(f"  - [Node {node_id}] ({component_type or 'Node'}) Set error_policy to '{new_policy}'")
                    else:
                        # Add explicit error_policy input to node
                        inputs.append({
                            "name": "error_policy",
                            "type": "ErrorPolicy",
                            "value": new_policy
                        })
                        changes_count += 1
                        logger.info(f"  - [Node {node_id}] ({component_type or 'Node'}) Added error_policy='{new_policy}'")

    return changes_count


if __name__ == "__main__":
    args = parse_args()

    _config_file_path: Optional[str] = None

    try:
        _config_file_path = config_cpdctl(args.host, args.username, args.password)
        project_id = get_project_id(args.project_name)

        if not project_id:
            logger.error(f"Project '{args.project_name}' not found.")
            sys.exit(1)

        pipeline_name = args.pipeline_name if args.scenario == "pipeline" else None
        pipelines_to_process = get_pipeline_ids(project_id, pipeline_name)

        if not pipelines_to_process:
            logger.warning("No matching pipelines found.")
            sys.exit(0)

        logger.info(f"Found {len(pipelines_to_process)} pipeline(s) to process. Scope: {args.scope}, Target Policy: {args.policy}")

        for pipeline in pipelines_to_process:
            pipe_id = pipeline.get("id")
            pipe_name = pipeline.get("name", "Unnamed")

            try:
                logger.info(f"Processing pipeline: '{pipe_name}' (ID: {pipe_id})")
                flow = get_pipeline_template(project_id, pipe_id)
                
                changes = process_error_policy(
                    flow=flow,
                    new_policy=args.policy,
                    scope=args.scope
                )

                if changes > 0:
                    logger.info(f"Saving changes for '{pipe_name}' ({changes} modifications)...")
                    update_flow(flow, project_id, pipe_id)
                    logger.info(f"Successfully updated '{pipe_name}'.")
                else:
                    logger.info(f"No changes required for '{pipe_name}'.")

            except subprocess.CalledProcessError as e:
                logger.error(f"Command '{e.cmd}' failed with return code {e.returncode}.\nStderr: {e.stderr}")
            except Exception as e:
                logger.error(f"Failed to process pipeline '{pipe_name}': {e}")

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")

    finally:
        if _config_file_path and os.path.exists(_config_file_path):
            os.remove(_config_file_path)