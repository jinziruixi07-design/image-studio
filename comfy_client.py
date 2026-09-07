"""Small helper for talking to a running ComfyUI server's HTTP API."""

import json
import urllib.parse
from pathlib import Path

import requests

WORKFLOWS_DIR = Path(__file__).parent / "workflows"


def list_workflows():
    """Return [{id, label, description, reference_labels}] for every workflow."""
    items = []
    for meta_path in sorted(WORKFLOWS_DIR.glob("*.meta.json")):
        workflow_id = meta_path.name[: -len(".meta.json")]
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        items.append({
            "id": workflow_id,
            "label": meta.get("label", workflow_id),
            "description": meta.get("description", ""),
            "reference_labels": meta.get("reference_labels", []),
        })
    return items


def load_workflow(workflow_id):
    workflow_path = WORKFLOWS_DIR / f"{workflow_id}.json"
    meta_path = WORKFLOWS_DIR / f"{workflow_id}.meta.json"
    if not workflow_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"unknown workflow id: {workflow_id}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return workflow, meta


def apply_overrides(workflow, meta, prompt=None, negative=None, seed=None, reference_images=None):
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

    reference_nodes = meta.get("reference_nodes") or []
    if reference_nodes and reference_images:
        for node_id, comfy_image_name in zip(reference_nodes, reference_images):
            workflow[node_id]["inputs"]["image"] = comfy_image_name


def upload_image(base_url, filename, file_bytes, content_type="image/png"):
    """Upload a reference image into ComfyUI's input/ folder; returns ComfyUI's name for it."""
    resp = requests.post(
        f"{base_url}/upload/image",
        files={"image": (filename, file_bytes, content_type)},
        data={"overwrite": "true"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["name"]


class ComfyUIRejectedPrompt(RuntimeError):
    """ComfyUI refused to even queue the workflow (e.g. a missing custom
    node or a bad model filename) - as opposed to a network-level failure."""


def _describe_prompt_rejection(resp):
    try:
        body = resp.json()
    except ValueError:
        return f"ComfyUIがリクエストを拒否しました (HTTP {resp.status_code})。"

    messages = []
    for node_id, info in (body.get("node_errors") or {}).items():
        for err in info.get("errors", []):
            messages.append(f"ノード#{node_id} ({info.get('class_type', '?')}): {err.get('message', err)}")

    if not messages and isinstance(body.get("error"), dict):
        messages.append(body["error"].get("message", str(body["error"])))

    if not messages:
        messages.append(str(body))

    return "ComfyUIがこのワークフローを実行できませんでした: " + " / ".join(messages)


def queue_prompt(base_url, workflow, client_id):
    resp = requests.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    if resp.status_code == 400:
        raise ComfyUIRejectedPrompt(_describe_prompt_rejection(resp))
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def get_history(base_url, prompt_id):
    """Return the ComfyUI history entry for prompt_id, or None if not finished yet."""
    resp = requests.get(f"{base_url}/history/{prompt_id}", timeout=30)
    resp.raise_for_status()
    history = resp.json()
    return history.get(prompt_id)


def get_execution_error(history_entry):
    """Return {node_type, exception_message} if ComfyUI reported an execution
    error for this prompt, otherwise None."""
    messages = history_entry.get("status", {}).get("messages", [])
    for kind, payload in messages:
        if kind == "execution_error":
            return {
                "node_type": payload.get("node_type", "unknown"),
                "exception_message": payload.get("exception_message", ""),
            }
    return None


def find_output_images(history_entry, save_node):
    """Return the list of every image produced by save_node (one per batch item)."""
    outputs = history_entry.get("outputs", {})
    node_output = outputs.get(save_node)
    if not node_output or "images" not in node_output:
        raise RuntimeError(f"画像が生成されませんでした(ノード {save_node} に出力がありません)")
    return node_output["images"]


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
