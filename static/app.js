const form = document.getElementById("generate-form");
const workflowSelect = document.getElementById("workflow_id");
const statusEl = document.getElementById("status");
const generateBtn = document.getElementById("generate-btn");
const resultEl = document.getElementById("result");
const resultImage = document.getElementById("result-image");
const downloadLink = document.getElementById("download-link");

async function loadWorkflows() {
  const res = await fetch("/api/workflows");
  const workflows = await res.json();
  workflowSelect.innerHTML = "";
  for (const wf of workflows) {
    const opt = document.createElement("option");
    opt.value = wf.id;
    opt.textContent = wf.label;
    workflowSelect.appendChild(opt);
  }
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

async function pollStatus(promptId) {
  while (true) {
    const res = await fetch(`/api/status/${promptId}`);
    const data = await res.json();

    if (data.status === "done") {
      return data.image_url;
    }
    if (data.status === "error") {
      throw new Error(data.error || "生成中にエラーが発生しました");
    }
    setStatus("生成中... (ComfyUIの処理が終わるまでお待ちください)");
    await new Promise((r) => setTimeout(r, 1500));
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  generateBtn.disabled = true;
  resultEl.hidden = true;
  setStatus("送信中...");

  const seedValue = document.getElementById("seed").value;

  const body = {
    workflow_id: workflowSelect.value,
    prompt: document.getElementById("prompt").value,
    negative: document.getElementById("negative").value,
    seed: seedValue === "" ? null : Number(seedValue),
  };

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "生成の開始に失敗しました");
    }

    const imageUrl = await pollStatus(data.prompt_id);
    resultImage.src = imageUrl;
    downloadLink.href = imageUrl;
    resultEl.hidden = false;
    setStatus("完成しました。");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    generateBtn.disabled = false;
  }
});

loadWorkflows().catch((err) => setStatus("ワークフロー一覧の取得に失敗しました: " + err.message, true));
