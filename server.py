"""Standalone image-generation website.

Run this, open http://127.0.0.1:5000 in a browser, type a prompt, click
generate. This process talks to a separately-running ComfyUI server (see
README.md) over HTTP; it has no dependency on any game project.
"""

import json
import os
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, abort

load_dotenv()

import comfy_client
import prompt_expand

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

CHARACTERS_DIR = Path(__file__).parent / "characters"
CHARACTERS_DIR.mkdir(exist_ok=True)
CHARACTERS_INDEX = CHARACTERS_DIR / "index.json"

app = Flask(__name__, static_folder="static", static_url_path="")

# In-memory job tracking. This tool is meant for a single local user, so a
# process-lifetime dict is enough; nothing here needs to survive a restart.
JOBS = {}


@app.errorhandler(Exception)
def handle_any_error(exc):
    """Always return JSON, even for errors this code didn't anticipate.

    Without this, an unhandled exception (or a plain 404) renders Flask's
    default HTML error page, and the frontend's `await res.json()` then
    fails with a confusing "Unexpected token '<' ... not valid JSON" - the
    browser is just reporting that the "JSON" it got was actually HTML.
    """
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        message = HTTP_ERROR_MESSAGES_JA.get(exc.code, f"エラーが発生しました (HTTP {exc.code})。")
        return jsonify({"error": message}), exc.code
    return jsonify({"error": f"サーバー内部で予期しないエラーが発生しました: {exc}"}), 500


HTTP_ERROR_MESSAGES_JA = {
    400: "リクエストの内容に誤りがあります。",
    404: "指定されたページ・データが見つかりませんでした。",
    405: "その操作はこのURLでは許可されていません。",
    413: "アップロードしたファイルが大きすぎます。",
    502: "ComfyUIサーバーからの応答が正常ではありませんでした。",
    503: "サーバーが一時的に利用できません。少し待って再度お試しください。",
    504: "ComfyUIサーバーからの応答がタイムアウトしました。",
}


def load_characters():
    if not CHARACTERS_INDEX.exists():
        return []
    return json.loads(CHARACTERS_INDEX.read_text(encoding="utf-8"))


def save_characters(characters):
    CHARACTERS_INDEX.write_text(json.dumps(characters, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/workflows")
def api_workflows():
    return jsonify(comfy_client.list_workflows())


@app.route("/api/features")
def api_features():
    return jsonify({"prompt_expansion_available": prompt_expand.is_available()})


@app.route("/api/expand_prompt", methods=["POST"])
def api_expand_prompt():
    if not prompt_expand.is_available():
        return jsonify({"error": "この機能を使うにはANTHROPIC_API_KEYの設定が必要です。"}), 400

    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    kind = data.get("kind") or "positive"
    if not text:
        return jsonify({"error": "変換したい文章を入力してください。"}), 400

    try:
        expanded = prompt_expand.expand_prompt(text, kind=kind)
    except Exception as exc:  # noqa: BLE001 - surface any API error to the UI
        return jsonify({"error": f"プロンプト変換に失敗しました: {exc}"}), 502

    return jsonify({"prompt": expanded})


@app.route("/api/characters", methods=["GET"])
def api_characters_list():
    return jsonify(load_characters())


@app.route("/api/characters", methods=["POST"])
def api_characters_create():
    name = (request.form.get("name") or "").strip()
    prompt_id = request.form.get("prompt_id")
    index_str = request.form.get("image_index")

    if not name:
        return jsonify({"error": "キャラクター名を入力してください。"}), 400
    if prompt_id is None or index_str is None:
        return jsonify({"error": "保存する画像を選択してください。"}), 400

    job = JOBS.get(prompt_id)
    if job is None or job.get("status") != "done":
        return jsonify({"error": "その画像は見つかりませんでした。"}), 404

    idx = int(index_str)
    local_path = _ensure_local_image(prompt_id, idx)
    if local_path is None:
        return jsonify({"error": "その画像は見つかりませんでした。"}), 404

    character_id = uuid.uuid4().hex[:12]
    portrait_name = f"{character_id}.png"
    (CHARACTERS_DIR / portrait_name).write_bytes(local_path.read_bytes())

    characters = load_characters()
    characters.append({
        "id": character_id,
        "name": name,
        "portrait": portrait_name,
        "created_at": time.time(),
    })
    save_characters(characters)

    return jsonify({"id": character_id, "name": name, "portrait_url": f"/api/characters/{character_id}/portrait"})


@app.route("/api/characters/<character_id>/portrait")
def api_character_portrait(character_id):
    characters = load_characters()
    match = next((c for c in characters if c["id"] == character_id), None)
    if match is None:
        abort(404)
    return send_from_directory(CHARACTERS_DIR, match["portrait"], mimetype="image/png")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    workflow_id = request.form.get("workflow_id")
    prompt = (request.form.get("prompt") or "").strip()
    negative = (request.form.get("negative") or "").strip()
    seed = request.form.get("seed")
    seed = int(seed) if seed not in (None, "") else None

    if not workflow_id:
        return jsonify({"error": "workflow_id is required"}), 400
    if not prompt:
        return jsonify({"error": "プロンプトを入力してください。"}), 400

    try:
        workflow, meta = comfy_client.load_workflow(workflow_id)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    reference_nodes = meta.get("reference_nodes") or []
    reference_image_names = []

    if reference_nodes:
        # An existing saved character can stand in for an uploaded file.
        character_id = request.form.get("character_id")
        if character_id:
            characters = load_characters()
            match = next((c for c in characters if c["id"] == character_id), None)
            if match is None:
                return jsonify({"error": "指定されたキャラクターが見つかりませんでした。"}), 404
            portrait_path = CHARACTERS_DIR / match["portrait"]
            try:
                comfy_name = comfy_client.upload_image(
                    COMFYUI_URL, f"character_{character_id}.png", portrait_path.read_bytes()
                )
            except requests.exceptions.RequestException as exc:
                return jsonify({"error": f"ComfyUIとの通信に失敗しました。ComfyUIが起動しているか確認してください ({COMFYUI_URL})。詳細: {exc}"}), 502
            reference_image_names.append(comfy_name)

        i = 0
        while True:
            file = request.files.get(f"reference_{i}")
            if file is None:
                break
            try:
                comfy_name = comfy_client.upload_image(COMFYUI_URL, file.filename, file.read(), file.mimetype)
            except requests.exceptions.RequestException as exc:
                return jsonify({"error": f"ComfyUIとの通信に失敗しました。ComfyUIが起動しているか確認してください ({COMFYUI_URL})。詳細: {exc}"}), 502
            reference_image_names.append(comfy_name)
            i += 1

        min_references = meta.get("min_references", len(reference_nodes))
        if len(reference_image_names) < min_references:
            return jsonify({"error": "参照画像を少なくとも1枚指定してください。"}), 400

        # Fewer images than reference slots is fine - repeat the last one to
        # fill the remaining slots in the (fixed-shape) ComfyUI graph.
        while len(reference_image_names) < len(reference_nodes):
            reference_image_names.append(reference_image_names[-1])

    comfy_client.apply_overrides(
        workflow, meta, prompt=prompt, negative=negative, seed=seed, reference_images=reference_image_names
    )

    client_id = str(uuid.uuid4())
    try:
        prompt_id = comfy_client.queue_prompt(COMFYUI_URL, workflow, client_id)
    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": f"ComfyUIに接続できませんでした。ComfyUIが起動しているか確認してください ({COMFYUI_URL})。",
        }), 502
    except comfy_client.ComfyUIRejectedPrompt as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - surface any other error to the UI
        return jsonify({"error": f"生成の開始に失敗しました: {exc}"}), 502

    JOBS[prompt_id] = {"status": "pending", "meta": meta, "created_at": time.time()}
    return jsonify({"prompt_id": prompt_id})


@app.route("/api/status/<prompt_id>")
def api_status(prompt_id):
    job = JOBS.get(prompt_id)
    if job is None:
        return jsonify({"error": "指定された生成ジョブが見つかりませんでした。"}), 404

    if job["status"] == "done":
        return jsonify({
            "status": "done",
            "image_urls": [f"/api/image/{prompt_id}/{i}" for i in range(len(job["image_infos"]))],
            "prompt_id": prompt_id,
        })

    try:
        history_entry = comfy_client.get_history(COMFYUI_URL, prompt_id)
    except requests.exceptions.ConnectionError:
        return jsonify({
            "status": "error",
            "error": (
                "ComfyUIに接続できなくなりました。GPUメモリ不足で生成中にComfyUIが"
                "落ちた可能性があります(comfyui.logに『CUDA out of memory』のような行が"
                "無いか確認してください)。ComfyUIを再起動して、参照画像を減らすか、"
                "同時生成枚数を減らして再度お試しください。"
            ),
        }), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"status": "error", "error": f"ComfyUIの状態確認に失敗しました: {exc}"}), 502

    if history_entry is None:
        return jsonify({"status": "pending"})

    execution_error = comfy_client.get_execution_error(history_entry)
    if execution_error:
        job["status"] = "error"
        return jsonify({
            "status": "error",
            "error": (
                f"ComfyUIでの生成中にエラーが発生しました"
                f"(ノード種別: {execution_error['node_type']})。"
                f" モデルファイルや必要なカスタムノードが揃っているか確認してください。"
                f" 詳細: {execution_error['exception_message']}"
            ),
        }), 502

    try:
        image_infos = comfy_client.find_output_images(history_entry, job["meta"]["save_node"])
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        return jsonify({"status": "error", "error": str(exc)}), 502

    job["status"] = "done"
    job["image_infos"] = image_infos
    return jsonify({
        "status": "done",
        "image_urls": [f"/api/image/{prompt_id}/{i}" for i in range(len(image_infos))],
        "prompt_id": prompt_id,
    })


def _ensure_local_image(prompt_id, idx):
    job = JOBS.get(prompt_id)
    if job is None or job.get("status") != "done":
        return None
    image_infos = job.get("image_infos") or []
    if idx < 0 or idx >= len(image_infos):
        return None

    local_name = f"{prompt_id}_{idx}.png"
    local_path = OUTPUTS_DIR / local_name
    if not local_path.exists():
        image_bytes = comfy_client.fetch_image_bytes(COMFYUI_URL, image_infos[idx])
        local_path.write_bytes(image_bytes)
    return local_path


@app.route("/api/image/<prompt_id>/<int:idx>")
def api_image(prompt_id, idx):
    local_path = _ensure_local_image(prompt_id, idx)
    if local_path is None:
        abort(404)
    return send_from_directory(OUTPUTS_DIR, local_path.name, mimetype="image/png")


if __name__ == "__main__":
    # HOST=0.0.0.0 is used when running behind a tunnel (e.g. the Colab
    # notebook in colab/) so the process accepts connections from outside
    # the machine it runs on. Debug/reloader is off by default in that case
    # since the reloader's subprocess forking doesn't play well with being
    # launched as a background job.
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "0" if host != "127.0.0.1" else "1") == "1"
    app.run(host=host, port=5000, debug=debug)
