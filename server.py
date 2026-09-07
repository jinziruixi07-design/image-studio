"""Standalone image-generation website.

Run this, open http://127.0.0.1:5000 in a browser, type a prompt, click
generate. This process talks to a separately-running ComfyUI server (see
README.md) over HTTP; it has no dependency on any game project.
"""

import os
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory, abort

import comfy_client

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")

# In-memory job tracking. This tool is meant for a single local user, so a
# process-lifetime dict is enough; nothing here needs to survive a restart.
JOBS = {}


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/workflows")
def api_workflows():
    return jsonify(comfy_client.list_workflows())


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(force=True)
    workflow_id = data.get("workflow_id")
    prompt = (data.get("prompt") or "").strip()
    negative = (data.get("negative") or "").strip()
    seed = data.get("seed")

    if not workflow_id:
        return jsonify({"error": "workflow_id is required"}), 400
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        workflow, meta = comfy_client.load_workflow(workflow_id)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    comfy_client.apply_overrides(workflow, meta, prompt=prompt, negative=negative, seed=seed)

    client_id = str(uuid.uuid4())
    try:
        prompt_id = comfy_client.queue_prompt(COMFYUI_URL, workflow, client_id)
    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": f"ComfyUIに接続できませんでした。ComfyUIが起動しているか確認してください ({COMFYUI_URL})。",
        }), 502
    except Exception as exc:  # noqa: BLE001 - surface any other error to the UI
        return jsonify({"error": f"生成の開始に失敗しました: {exc}"}), 502

    JOBS[prompt_id] = {"status": "pending", "meta": meta, "created_at": time.time()}
    return jsonify({"prompt_id": prompt_id})


@app.route("/api/status/<prompt_id>")
def api_status(prompt_id):
    job = JOBS.get(prompt_id)
    if job is None:
        return jsonify({"error": "unknown prompt_id"}), 404

    if job["status"] == "done":
        return jsonify({"status": "done", "image_url": f"/api/image/{prompt_id}"})

    try:
        history_entry = comfy_client.get_history(COMFYUI_URL, prompt_id)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"status": "error", "error": str(exc)}), 502

    if history_entry is None:
        return jsonify({"status": "pending"})

    try:
        image_info = comfy_client.find_output_image(history_entry, job["meta"]["save_node"])
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        return jsonify({"status": "error", "error": str(exc)}), 502

    job["status"] = "done"
    job["image_info"] = image_info
    return jsonify({"status": "done", "image_url": f"/api/image/{prompt_id}"})


@app.route("/api/image/<prompt_id>")
def api_image(prompt_id):
    job = JOBS.get(prompt_id)
    if job is None or job.get("status") != "done":
        abort(404)

    local_name = f"{prompt_id}.png"
    local_path = OUTPUTS_DIR / local_name
    if not local_path.exists():
        image_bytes = comfy_client.fetch_image_bytes(COMFYUI_URL, job["image_info"])
        local_path.write_bytes(image_bytes)

    return send_from_directory(OUTPUTS_DIR, local_name, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
