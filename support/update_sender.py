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
     --sender-value   New value

    Value of sender addr format:
    - standalone string, ex. sample.sender@test.com
    - user variable, parameter set, pipeline parameter in format:
        - for pipeline parameter: #parameter_name#
        - for user_variable: #UsrVar.variable_name#
        - for parameter set: #parameter_set_name.variable_name#
    - concatenation on strings with parameters, ex. some_prefix#parameter_set_name.variable_name#some_suffix

   Example:
     python update_sender.py project \
         --host https://cpd-cpd-instance.cp.fyre.ibm.com \
         --username admin \
         --password secret \
         --project-name MyProject \
         --sender-value #$Ev_EMAIL_SENDERS_LIST#

    python update_sender.py project \
         --host https://cpd-cpd-instance.cp.fyre.ibm.com \
         --username admin \
         --password secret \
         --project-name MyProject \
         --sender-value #ParameterSetName.ParamName#@sample.com

2. Project-Wide Update (File-based, specific nodes)

   Updates specific 'Send email' nodes in specific pipelines based on a file.
   The file format must be: pipeline_name,node_name,sender_value

   Required arguments:
     --host           URL of the server or service
     --username       Authentication username
     --password       Authentication password
     --project-name   Name of the project to update
     --path           Path to the update specification file

   Example (file contents):
     PipelineA, Node1_Send_Email, test.sample#sender_set.sender_addr_A#.com
     PipelineA, Node5_Send_Email, #sender_param_B#
     PipelineB, Node_Notify_Admin, #sender_param_B#.sample.com

   Example command:
     python update_sender.py project \
         --host https://cpd-cpd-instance.cp.fyre.ibm.com \
         --username admin \
         --password secret \
         --project-name MyProject \
         --path /path/to/file.txt

3. Single Pipeline Update

   Updates the sender parameter in a specific pipeline within the project.

   Required arguments:
     --host           URL of the server or service
     --username       Authentication username
     --password       Authentication password
     --project-name   Name of the project
     --pipeline-name  Name of the specific pipeline to update
     --sender-value   New value

    Value of sender addr format:
    - standalone string, ex. sample.sender@test.com
    - user variable, parameter set, pipeline parameter in format:
        - for pipeline parameter: #parameter_name#
        - for user_variable: #UsrVar.variable_name#
        - for parameter set: #parameter_set_name.variable_name#
    - concatenation on strings with parameters, ex. some_prefix#parameter_set_name.variable_name#some_suffix

   Example:
     python update_sender.py pipeline \
         --host https://cpd-cpd-instance.cp.fyre.ibm.com \
         --username admin \
         --password secret \
         --project-name MyProject \
         --pipeline-name PipelineA \
         --sender-value #sender_param_name#
"""
import os
import sys
import json
import logging
import argparse
import subprocess
import tempfile
import re
import csv
import zipfile
import shutil
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Any, Union, Optional

JSONType = Union[Dict[str, Any], List[Any]]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEBUG_DIR = os.path.join(SCRIPT_DIR, "debug_temp")

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
DEBUG_ARCHIVE_NAME = os.path.join(SCRIPT_DIR, f"debug_update_sender_logs_{timestamp}.zip")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("UpdateSender")


@dataclass
class UpdateInstruction:
    pipeline_name: str
    node_name: str
    raw_value: str


class ExpressionResolver:

    def __init__(self, flow_context: Dict[str, List[str]]):
        self.context = flow_context

    def resolve(self, input_value: str) -> str:
        parts = re.split(r'#([^#]+)#', input_value)
        expression_parts = []

        for i, token in enumerate(parts):
            if i % 2 == 0:
                if token:
                    expression_parts.append(json.dumps(token))
            else:
                resolved = self._resolve_single_variable(token)
                if resolved:
                    expression_parts.append(resolved)
                else:
                    raise ValueError(f"Variable '{token}' found in input but not defined in pipeline context.")

        if not expression_parts:
            return json.dumps("")

        return " + ".join(expression_parts)

    def _resolve_single_variable(self, token: str) -> Optional[str]:

        # After-migration usr var format
        migrated_var_name = token.replace(".", "_")
        if migrated_var_name in self.context["user_vars"]:
            return f'vars.{migrated_var_name}'

        # User variables
        if token.startswith("UsrVar."):
            var_name = token.split(".", 1)[1]
            if var_name in self.context["user_vars"]:
                return f'vars.{var_name}'

        # Parameter sets
        if "." in token:
            set_name, param_name = token.split(".", 1)
            if set_name in self.context["param_sets"]:
                return f'param_sets.{set_name}["{param_name}"]'

        # Pipeline Parameters
        if token in self.context["pipeline_params"]:
            return f'params["{token}"]'

        return None


class CPDClient:

    def __init__(self, host: str, username: str, password: str):
        self._env = os.environ.copy()
        self._config_file = self._setup_config(host, username, password)

    def _setup_config(self, host: str, username: str, password: str) -> str:
        tmp_config = tempfile.NamedTemporaryFile(mode='w+', delete=False)
        tmp_config.write("users:\nprofiles:")
        tmp_config.close()

        self._env["CPD_CONFIG"] = tmp_config.name

        try:
            self._exec([
                "cpdctl", "config", "profile", "set", "TMPPROFILE",
                "--url", host,
                "--username", username,
                "--password", password
            ])
        except Exception:
            self.cleanup()
            raise

        return tmp_config.name

    def _exec(self, args: list[str]) -> bytes:
        logger.debug(f"Executing: {' '.join(args[:4])} ...")
        p = subprocess.Popen(
            args=args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env
        )
        stdout, stderr = p.communicate()

        if p.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error(f"Command failed: {err_msg}")
            raise subprocess.CalledProcessError(p.returncode, args[0], stderr=err_msg)

        return stdout

    def get_project_id(self, project_name: str) -> Optional[str]:
        output = self._exec(["cpdctl", "project", "list", "-n", project_name, "--output", "json"])
        data = json.loads(output)
        if data.get("total_results", 0) > 0:
            return data["resources"][0]["metadata"]["guid"]
        return None

    def list_pipelines(self, project_id: str) -> List[Dict]:
        pipelines = []
        page_token = None
        while True:
            cmd = ["cpdctl", "pipeline", "list", "--project-id", project_id, "--page-size", "100", "--output", "json"]
            if page_token:
                cmd.extend(["--page-token", page_token])

            result = json.loads(self._exec(cmd))
            pipelines.extend(result.get("pipelines", []))
            page_token = result.get("next_page_token")
            if not page_token:
                break
        return pipelines

    def get_pipeline_flow(self, project_id: str, pipeline_id: str) -> JSONType:
        stdout = self._exec([
            "cpdctl", "pipeline", "get-template",
            "--project-id", project_id,
            "--pipeline-id", pipeline_id,
            "--version", "any",
            "--format", "flow",
            "--output", "json"
        ])

        full_response = json.loads(stdout)
        if "flow" in full_response:
            return json.loads(full_response["flow"])
        else:
            raise ValueError("Response did not contain 'flow' key.")

    def upload_pipeline_flow(self, flow: JSONType, project_id: str, pipeline_id: str):
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as tmp:
            json.dump(flow, tmp, indent=2)
            tmp_path = tmp.name

        logger.info(f"Uploading updated flow for pipeline ID: {pipeline_id}")

        try:
            self._exec([
                "cpdctl", "pipeline", "version", "upload",
                "--file", tmp_path,
                "--project-id", project_id,
                "--pipeline-id", pipeline_id,
                "--volatile", "true"
            ])
            logger.info(f"Successfully uploaded updated flow for pipeline ID: {pipeline_id}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def cleanup(self):
        if hasattr(self, '_config_file') and os.path.exists(self._config_file):
            try:
                os.remove(self._config_file)
            except OSError:
                pass


class PipelineProcessor:

    def __init__(self, flow: JSONType):
        self.flow = flow
        self.context = self._extract_context(flow)
        self.resolver = ExpressionResolver(self.context)

    def _extract_context(self, flow: JSONType) -> Dict[str, List[str]]:
        app_data = flow.get("app_data", {})
        pipeline_data = app_data.get("pipeline_data", {})

        user_vars = [v["name"] for v in pipeline_data.get("variables", [])]
        param_sets = [p["name"] for p in pipeline_data.get("parameter_sets", [])]

        primary_id = flow.get("primary_pipeline", "")
        pipelines = flow.get("pipelines", [])
        primary_pipe = next((p for p in pipelines if p.get("id") == primary_id), {})
        pp_data = primary_pipe.get("app_data", {}).get("pipeline_data", {})
        pipeline_params = [p["name"] for p in pp_data.get("inputs", [])]

        ctx = {
            "user_vars": user_vars,
            "param_sets": param_sets,
            "pipeline_params": pipeline_params
        }

        logger.debug(f"Pipeline context: {ctx}")

        return ctx

    def update_send_email_nodes(self, updates: Dict[Union[str, None], str]) -> Dict[str, str]:

        applied_updates = {}
        pipelines_list = self.flow.get("pipelines", [])

        for pipeline in pipelines_list:
            nodes = pipeline.get("nodes", [])
            for node in nodes:
                app_data = node.get("app_data", {})
                if app_data.get("componentLabelRef") != "Send email":
                    continue

                node_pipeline_data = app_data.get("pipeline_data", {})
                node_ui_data = app_data.get("ui_data", {})
                
                node_name = node_pipeline_data.get("descriptive_name", "") or node_ui_data.get("label", "")

                target_value = updates.get(node_name) or updates.get(None)

                if target_value:
                    try:
                        expression = self.resolver.resolve(target_value)
                        self._apply_update(node_pipeline_data, expression)
                        logger.debug(f"Updated node '{node_name}' with expression: {expression}")

                        applied_updates[node_name] = expression

                    except ValueError as e:
                        logger.error(f"Skipping node '{node_name}' in pipeline: {e}")
                        raise

        return applied_updates

    def _apply_update(self, node_data: Dict, expression: str):
        inputs = node_data.get("inputs", [])
        for inp in inputs:
            if inp.get("name") == "sender_addr":
                inp.pop("value", None)
                inp.pop("ui_data", None)
                inp["value_from"] = {"expression": expression}
                return
        logger.warning("Found 'Send email' node but 'sender_addr' input was missing.")


def validate_pipeline_changes(client: CPDClient, project_id: str, pipeline_id: str,
                              expected_changes: Dict[Union[str, None], str]):
    pass


def parse_csv_file(file_path: str) -> List[UpdateInstruction]:
    instructions = []
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found.")

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, 1):
            if not row:
                continue
            if len(row) != 3:
                logger.warning(f"Line {i}: Expected 3 columns, got {len(row)}. Skipping.")
                continue

            instructions.append(UpdateInstruction(
                pipeline_name=row[0].strip(),
                node_name=row[1].strip(),
                raw_value=row[2].strip()
            ))
    return instructions


def dump_failed_flow(flow_data: dict, pipeline_name: str, pipeline_id: str, reason: str):
    if not os.path.exists(DEBUG_DIR):
        try:
            os.makedirs(DEBUG_DIR)
        except OSError:
            pass

    filename = os.path.join(DEBUG_DIR, f"{pipeline_id}_{reason}.json")

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(flow_data, f)
            f.flush()
            os.fsync(f.fileno())
        logger.info(f"Dumped logs for debugging: {filename}")
    except Exception as e:
        logger.error(f"Failed to dump debug flow JSON: {e}")


def create_debug_archive():
    if not os.path.exists(DEBUG_DIR):
        return

    if not os.listdir(DEBUG_DIR):
        shutil.rmtree(DEBUG_DIR)
        return

    logger.info(f"Creating debug archive: {DEBUG_ARCHIVE_NAME}")

    try:
        with zipfile.ZipFile(DEBUG_ARCHIVE_NAME, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(DEBUG_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, arcname=file)
    except Exception as e:
        logger.error(f"Failed to create zip archive: {e}")
    finally:
        if os.path.exists(DEBUG_DIR):
            shutil.rmtree(DEBUG_DIR)
            logger.info("Cleaned up temporary debug files.")


def run_project_scenario(args, client: CPDClient, project_id: str):
    logger.info("Starting PROJECT scenario.")

    if args.path:
        logger.info(f"Reading update file: {args.path}")
        instructions = parse_csv_file(args.path)

        updates_by_pipeline = defaultdict(list)
        for instr in instructions:
            updates_by_pipeline[instr.pipeline_name].append(instr)

        logger.info(f"Found updates for {len(updates_by_pipeline)} distinct pipelines.")

        all_pipelines = client.list_pipelines(project_id)
        name_to_id = {p["name"]: p["id"] for p in all_pipelines}

        for pipe_name, instrs in updates_by_pipeline.items():
            if pipe_name not in name_to_id:
                logger.error(f"Pipeline '{pipe_name}' found in file but not in project. Skipping.")
                continue

            pid = name_to_id[pipe_name]
            logger.info(f"Processing pipeline '{pipe_name}' (ID: {pid})...")

            flow_data = None
            try:
                flow_data = client.get_pipeline_flow(project_id, pid)
                processor = PipelineProcessor(flow_data)

                node_updates_input = {instr.node_name: instr.raw_value for instr in instrs}

                applied_changes = processor.update_send_email_nodes(node_updates_input)

                requested_nodes = set(node_updates_input.keys())
                updated_nodes = set(applied_changes.keys())
                missed_nodes = requested_nodes - updated_nodes

                logger.debug(f"Mapped changes: {applied_changes}")

                if missed_nodes:
                    logger.warning(f"Nodes requested but NOT found in '{pipe_name}': {missed_nodes}")
                    if args.debug and flow_data:
                        dump_failed_flow(flow_data, pipe_name, pid, "partial_miss")

                elif applied_changes:
                    client.upload_pipeline_flow(processor.flow, project_id, pid)
                    if args.validate:
                        validate_pipeline_changes(client, project_id, pid, applied_changes)

                else:
                    logger.info(f"No nodes matched or updated in pipeline '{pipe_name}'.")
                    if args.debug and flow_data:
                        dump_failed_flow(flow_data, pipe_name, pid, "no_matches")

            except Exception as e:
                logger.error(f"Failed to process pipeline '{pipe_name}': {e}", exc_info=True)
                if args.debug and flow_data:
                    dump_failed_flow(flow_data, pipe_name, pid, "error")

    else:
        logger.info(f"Updating ALL pipelines with value: {args.sender_value}")
        pipelines = client.list_pipelines(project_id)

        global_updates_map = {None: args.sender_value}

        for p in pipelines:
            flow_data = None
            try:
                logger.info(f"Checking pipeline: {p['name']}")
                flow_data = client.get_pipeline_flow(project_id, p['id'])
                processor = PipelineProcessor(flow_data)

                applied_changes = processor.update_send_email_nodes(global_updates_map)

                if applied_changes:
                    client.upload_pipeline_flow(processor.flow, project_id, p['id'])
                    if args.validate:
                        validate_pipeline_changes(client, project_id, p['id'], applied_changes)
                else:
                    logger.info(f"No 'Send email' nodes found in '{p['name']}'.")
                    if args.debug and flow_data:
                        dump_failed_flow(flow_data, p['name'], p['id'], "no_email_nodes")

            except Exception as e:
                logger.error(f"Error processing pipeline {p['name']}: {e}", exc_info=True)
                if args.debug and flow_data:
                    dump_failed_flow(flow_data, p['name'], p['id'], "error")


def run_pipeline_scenario(args, client: CPDClient, project_id: str):
    logger.info(f"Starting PIPELINE scenario for '{args.pipeline_name}'")

    all_pipelines = client.list_pipelines(project_id)
    targets = [p for p in all_pipelines if p["name"] == args.pipeline_name]

    if not targets:
        logger.error(f"Pipeline '{args.pipeline_name}' not found in project.")
        sys.exit(1)

    global_updates_map = {None: args.sender_value}

    for target in targets:
        flow_data = None
        try:
            logger.info(f"Processing ID: {target['id']}")
            flow_data = client.get_pipeline_flow(project_id, target['id'])
            processor = PipelineProcessor(flow_data)

            applied_changes = processor.update_send_email_nodes(global_updates_map)

            if applied_changes:
                client.upload_pipeline_flow(processor.flow, project_id, target['id'])
                if args.validate:
                    validate_pipeline_changes(client, project_id, target['id'], applied_changes)
            else:
                logger.warning(f"No 'Send email' nodes updated in pipeline '{target['name']}'.")
                if args.debug and flow_data:
                    dump_failed_flow(flow_data, target['name'], target['id'], "no_changes")

        except Exception as e:
            logger.error(f"Error processing pipeline: {e}", exc_info=True)
            if args.debug and flow_data:
                dump_failed_flow(flow_data, target['name'], target['id'], "error")


def parse_args():
    parser = argparse.ArgumentParser(description="Update 'sender' parameter in Notification activities.")

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--host", required=True, help="CPD Host URL")
    parent_parser.add_argument("--username", required=True, help="Username")
    parent_parser.add_argument("--password", required=True, help="Password")
    parent_parser.add_argument("--project-name", required=True, help="Project Name")
    parent_parser.add_argument("--debug", action="store_true", help="Enable detailed debug logging and file output.")
    parent_parser.add_argument("--validate", action="store_true", help="Validate changes after upload.")

    subparsers = parser.add_subparsers(dest="scenario", required=True, title="Scenarios")

    proj_parser = subparsers.add_parser("project", parents=[parent_parser],
                                        help="Update across project (all or file-based).")
    proj_group = proj_parser.add_mutually_exclusive_group(required=True)
    proj_group.add_argument("--sender-value", help="Global value for all nodes.")
    proj_group.add_argument("--path", help="CSV file mapping: pipeline,node,value")

    pipe_parser = subparsers.add_parser("pipeline", parents=[parent_parser],
                                        help="Update single pipeline.")
    pipe_parser.add_argument("--pipeline-name", required=True, help="Pipeline Name")
    pipe_parser.add_argument("--sender-value", required=True, help="New sender value")

    return parser.parse_args()


def setup_debug_logging(args):
    if args.debug:

        if os.path.exists(DEBUG_DIR):
            try:
                shutil.rmtree(DEBUG_DIR)
                logger.debug(f"Cleaning existing DEBUG directory: {DEBUG_DIR}")
            except Exception as e:
                logger.warning(f"Could not clean debug directory: {e}")

        if not os.path.exists(DEBUG_DIR):
            os.makedirs(DEBUG_DIR)

        log_file_path = os.path.join(DEBUG_DIR, 'debug_log.txt')

        fh = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        fh.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.addHandler(fh)
        root_logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

        logger.info(f"Debug logging enabled. Logs temporarily collecting in '{log_file_path}'.")

        log_args = vars(args).copy()
        if 'password' in log_args:
            log_args['password'] = '******'
        logger.debug(f"Parsed Arguments: {json.dumps(log_args, indent=2)}")


def main():
    args = parse_args()

    setup_debug_logging(args)

    client = None

    try:
        logger.info("Initializing CPD Client...")
        client = CPDClient(args.host, args.username, args.password)

        logger.info(f"Resolving project ID for '{args.project_name}'...")
        project_id = client.get_project_id(args.project_name)

        if not project_id:
            logger.error(f"Project '{args.project_name}' not found on server.")
            sys.exit(1)

        if args.scenario == "project":
            run_project_scenario(args, client, project_id)
        elif args.scenario == "pipeline":
            run_pipeline_scenario(args, client, project_id)

    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user.")
    except Exception as e:
        logger.critical(f"Unexpected fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if client:
            client.cleanup()

        if args.debug:
            create_debug_archive()

        logger.info("Cleanup complete.")


if __name__ == "__main__":
    main()
