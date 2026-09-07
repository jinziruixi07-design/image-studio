const form = document.getElementById("generate-form");
const workflowSelect = document.getElementById("workflow_id");
const workflowDescription = document.getElementById("workflow-description");
const referenceUploadsEl = document.getElementById("reference-uploads");
const characterPicker = document.getElementById("character-picker");
const characterSelect = document.getElementById("character_select");
const promptEl = document.getElementById("prompt");
const expandBtn = document.getElementById("expand-btn");
const statusEl = document.getElementById("status");
const generateBtn = document.getElementById("generate-btn");
const resultEl = document.getElementById("result");
const resultGrid = document.getElementById("result-grid");
const characterListEl = document.getElementById("character-list");

let workflows = [];

function currentWorkflow() {
  return workflows.find((w) => w.id === workflowSelect.value);
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function renderWorkflowExtras() {
  const wf = currentWorkflow();
  workflowDescription.textContent = wf ? wf.description || "" : "";
  referenceUploadsEl.innerHTML = "";
  characterPicker.hidden = true;

  if (!wf || !wf.reference_labels || wf.reference_labels.length === 0) return;

  if (wf.reference_labels.length === 1) {
    characterPicker.hidden = false;
  }

  wf.reference_labels.forEach((label, i) => {
    const wrapper = document.createElement("label");
    wrapper.className = "reference-upload";
    wrapper.dataset.index = String(i);

    const span = document.createElement("span");
    span.textContent = label;

    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";

    wrapper.appendChild(span);
    wrapper.appendChild(input);
    referenceUploadsEl.appendChild(wrapper);
  });

  applyCharacterSelectionVisibility();
}

function applyCharacterSelectionVisibility() {
  const firstUpload = referenceUploadsEl.querySelector('[data-index="0"]');
  if (!firstUpload) return;
  const usingCharacter = !characterPicker.hidden && characterSelect.value !== "";
  firstUpload.hidden = usingCharacter;
}

async function loadWorkflows() {
  const res = await fetch("/api/workflows");
  workflows = await res.json();
  workflowSelect.innerHTML = "";
  for (const wf of workflows) {
    const opt = document.createElement("option");
    opt.value = wf.id;
    opt.textContent = wf.label;
    workflowSelect.appendChild(opt);
  }
  renderWorkflowExtras();
}

async function loadFeatures() {
  const res = await fetch("/api/features");
  const data = await res.json();
  expandBtn.hidden = !data.prompt_expansion_available;
}

async function loadCharacters() {
  const res = await fetch("/api/characters");
  const characters = await res.json();

  characterSelect.innerHTML = '<option value="">-- 使わない(新しい画像をアップロード) --</option>';
  for (const c of characters) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    characterSelect.appendChild(opt);
  }

  characterListEl.innerHTML = "";
  if (characters.length === 0) {
    characterListEl.innerHTML = '<p class="hint">まだ保存したキャラクターはありません。</p>';
    return;
  }
  for (const c of characters) {
    const card = document.createElement("div");
    card.className = "character-card";
    card.innerHTML = `
      <img src="/api/characters/${c.id}/portrait" alt="${c.name}" />
      <div>${c.name}</div>
    `;
    characterListEl.appendChild(card);
  }
}

function renderResults(promptId, urls, isCharacterWorkflow) {
  resultGrid.innerHTML = "";
  urls.forEach((url, i) => {
    const item = document.createElement("div");
    item.className = "result-item";

    const img = document.createElement("img");
    img.src = url;
    img.alt = `生成結果 ${i + 1}`;
    item.appendChild(img);

    const actions = document.createElement("div");
    actions.className = "actions";

    const link = document.createElement("a");
    link.href = url;
    link.download = `generated_${i + 1}.png`;
    link.textContent = "ダウンロード";
    actions.appendChild(link);

    if (isCharacterWorkflow) {
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.textContent = "キャラクターとして保存";
      saveBtn.addEventListener("click", () => saveAsCharacter(promptId, i));
      actions.appendChild(saveBtn);
    }

    item.appendChild(actions);
    resultGrid.appendChild(item);
  });
}

async function saveAsCharacter(promptId, index) {
  const name = window.prompt("キャラクター名を入力してください");
  if (!name) return;

  const fd = new FormData();
  fd.append("name", name);
  fd.append("prompt_id", promptId);
  fd.append("image_index", String(index));

  const res = await fetch("/api/characters", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || "保存に失敗しました");
    return;
  }
  alert(`「${data.name}」として保存しました。`);
  loadCharacters();
}

async function pollStatus(promptId) {
  while (true) {
    const res = await fetch(`/api/status/${promptId}`);
    const data = await res.json();

    if (data.status === "done") {
      return data.image_urls;
    }
    if (data.status === "error") {
      throw new Error(data.error || "生成中にエラーが発生しました");
    }
    setStatus("生成中... (ComfyUIの処理が終わるまでお待ちください)");
    await new Promise((r) => setTimeout(r, 1500));
  }
}

workflowSelect.addEventListener("change", renderWorkflowExtras);
characterSelect.addEventListener("change", applyCharacterSelectionVisibility);

expandBtn.addEventListener("click", async () => {
  const text = promptEl.value.trim();
  if (!text) {
    setStatus("先に、欲しい画像の説明を書いてください。", true);
    return;
  }
  expandBtn.disabled = true;
  const originalLabel = expandBtn.textContent;
  expandBtn.textContent = "変換中...";
  try {
    const res = await fetch("/api/expand_prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "変換に失敗しました");
    promptEl.value = data.prompt;
    setStatus("プロンプトを変換しました。");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    expandBtn.disabled = false;
    expandBtn.textContent = originalLabel;
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const wf = currentWorkflow();
  if (!wf) return;

  generateBtn.disabled = true;
  resultEl.hidden = true;
  setStatus("送信中...");

  const formData = new FormData();
  formData.append("workflow_id", wf.id);
  formData.append("prompt", promptEl.value);
  formData.append("negative", document.getElementById("negative").value);
  const seedValue = document.getElementById("seed").value;
  if (seedValue !== "") formData.append("seed", seedValue);

  const usingCharacter = !characterPicker.hidden && characterSelect.value !== "";
  if (usingCharacter) {
    formData.append("character_id", characterSelect.value);
  }

  const fileInputs = referenceUploadsEl.querySelectorAll(".reference-upload:not([hidden]) input[type=file]");
  let missingFile = false;
  let idx = 0;
  for (const input of fileInputs) {
    if (!input.files[0]) {
      missingFile = true;
      break;
    }
    formData.append(`reference_${idx}`, input.files[0]);
    idx++;
  }

  if (missingFile) {
    setStatus("参照画像をすべて選択してください。", true);
    generateBtn.disabled = false;
    return;
  }

  try {
    const res = await fetch("/api/generate", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "生成の開始に失敗しました");
    }

    const urls = await pollStatus(data.prompt_id);
    renderResults(data.prompt_id, urls, wf.id.startsWith("character"));
    resultEl.hidden = false;
    setStatus("完成しました。");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    generateBtn.disabled = false;
  }
});

Promise.all([loadWorkflows(), loadFeatures(), loadCharacters()]).catch((err) =>
  setStatus("初期化に失敗しました: " + err.message, true)
);
