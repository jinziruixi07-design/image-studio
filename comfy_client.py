"""Small helper for talking to a running ComfyUI server's HTTP API."""

import json
import urllib.parse
from pathlib import Path

import requests

WORKFLOWS_DIR = Path(__file__).parent / "workflows"


def list_workflows():
    """Return [{id, label}] for every *.json/*.meta.json pair in workflows/."""
    items = []
    for meta_path in sorted(WORKFLOWS_DIR.glob("*.meta.json")):
        workflow_id = meta_path.name[: -len(".meta.json")]
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        items.append({"id": workflow_id, "label": meta.get("label", workflow_id)})
    return items


def load_workflow(workflow_id):
    workflow_path = WORKFLOWS_DIR / f"{workflow_id}.json"
    meta_path = WORKFLOWS_DIR / f"{workflow_id}.meta.json"
    if not workflow_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"unknown workflow id: {workflow_id}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return workflow, meta


def apply_overrides(workflow, meta, prompt=None, negative=None, seed=None):
    if prompt:
        node = meta["positive_node"]
        workflow[node]["inputs"][meta["positive_input"]] = prompt

    if negative:
        node = meta.get("negative_node")
        if node:
            workflow[node]["inputs"][meta["negative_input"]] = negative

    if seed is not None:
        node = meta["seed_node"]
        workflow[node]["inputs"][meta["seed_input"]] = seed


def queue_prompt(base_url, workflow, client_id):
    resp = requests.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def get_history(base_url, prompt_id):
    """Return the ComfyUI history entry for prompt_id, or None if not finished yet."""
    resp = requests.get(f"{base_url}/history/{prompt_id}", timeout=30)
    resp.raise_for_status()
    history = resp.json()
    return history.get(prompt_id)


def find_output_image(history_entry, save_node):
    outputs = history_entry.get("outputs", {})
    node_output = outputs.get(save_node)
    if not node_output or "images" not in node_output:
        raise RuntimeError(f"no image found in output of node {save_node}")
    return node_output["images"][0]


def fetch_image_bytes(base_url, image_info):
    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    url = f"{base_url}/view?{urllib.parse.urlencode(params)}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content
