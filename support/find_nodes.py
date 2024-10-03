#  IBM Confidential
#  OCO Source Materials
#  5737-B37, 5737-C49, 5737-H76
#  (C) Copyright IBM Corp. 2024 All Rights Reserved.
#  The source code for this program is not published or
#  otherwise divested of its trade secrets, irrespective of
#  what has been deposited with the U.S. Copyright Office.

# Usage:
#   python find_nodes.py --pipeline-file <saved pipeline json>
#
# Example:
#   python find_nodes.py --pipeline-file ./pipeline.json

import os
import re
import json
import base64
import shutil
import pathlib
import argparse
import subprocess
import socketserver
import re
import requests
from requests.adapters import HTTPAdapter
import urllib3
from datetime import datetime
import time
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

#############################


def extract_task_id_from_expr(args, expression):
    result = re.search(r"tasks\.([a-zA-Z0-9_]+)", expression)
    if result is None:
        return set()
    return set(result.groups())


def extract_ref_tasks(args, input):
    refs = set()
    vf = input.get("value_from")
    if vf is None:
        return refs
    if vf.get("expression") is not None:
        refs = refs.union(extract_task_id_from_expr(args, vf["expression"]))
    if vf.get("node_output") is not None:
        refs.add(vf["node_output"]["node_id_ref"])
    return refs


def extract_node(args, node):
    links = ()
    if "links" in node["inputs"][0]:
        links = [link["node_id_ref"] for link in node["inputs"][0]["links"] if "links" in node["inputs"][0]]
    node_def = {
        "id": node["id"],
        "name": node["app_data"]["pipeline_data"]["descriptive_name"],
        "type": node["app_data"]["pipeline_data"]["config"]["link"]["component_id_ref"],
        "task_refs_per_input": {},
        "links": links
    }
    refs = set()
    inputs = node["app_data"]["pipeline_data"]["inputs"]
    for inp in inputs:
        inp_refs = extract_ref_tasks(args, inp)
        node_def["task_refs_per_input"][inp["name"]] = inp_refs
        refs = refs.union(inp_refs)
    node_def["task_refs"] = refs
    return node_def


def follow_link(args, all_nodes, node, target, top_call=True):
    any_sequencer_on_path = False
    found = False
    target_node = all_nodes[target]
    for prev in node["links"]:
        prev = all_nodes[prev]
        if prev["id"] == target:
            found = True
            break
        else:
            if prev["type"] == "wait-sequencer-any":
                any_sequencer_on_path = True
            f, o = follow_link(args, all_nodes, prev, target, top_call=False)
            if o:
                any_sequencer_on_path = True
            if f:
                found = True
                break
    if top_call and found and any_sequencer_on_path:
        ainput = ""
        for inp_ref in node["task_refs_per_input"]:
            if target in node["task_refs_per_input"][inp_ref]:
                ainput = inp_ref
        print(f"Node \"{node['name']}\" : {ainput} is using output from \"{target_node['name']}\" via wait for any")
    return found, any_sequencer_on_path


def process_node(args, node, all_nodes):
    task_refs = node["task_refs"]
    if len(task_refs) == 0:
        return
    for ref_id in task_refs:
        follow_link(args, all_nodes, node, ref_id)


def process_pipeline(args, pipeline):
    all_nodes = {}
    pid = pipeline.get("id")
    nodes = pipeline.get("nodes")
    print(f"pipeline {pid} : nodes {len(nodes)}")
    for node in nodes:
        ndef = extract_node(args, node)
        all_nodes[ndef["id"]] = ndef
    for nid in all_nodes:
        node = all_nodes[nid]
        process_node(args, node, all_nodes)


def process_pipeline_file(args):
    with open(args.pipeline_file, 'r') as file:
        data = json.load(file)

    pipelines = data.get("pipelines")
    if pipelines is None:
        print("file does not contain any pipelines")
        exit(1)

    for pipeline in pipelines:
        process_pipeline(args, pipeline)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-id", type=str, help="pipeline-id")
    parser.add_argument("--pipeline-file", type=str, help="pipeline-id")

    args = parser.parse_args()

    if args.pipeline_id is None and args.pipeline_file is None:
        print(f"Missing ----pipeline-file parameter. Provide path to saved pipeline")
        exit(1)

    process_pipeline_file(args)


