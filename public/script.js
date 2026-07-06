const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const preview = document.getElementById("preview");
const hint = document.querySelector(".dropzone__hint");
const analyzeBtn = document.getElementById("analyzeBtn");
const statusEl = document.getElementById("status");
const resultsPanel = document.getElementById("resultsPanel");
const revEl = document.getElementById("rev");
const dateStamp = document.getElementById("dateStamp");
const descriptionInput = document.getElementById("descriptionInput");
const modeButtons = document.querySelectorAll(".mode-btn");

let selectedFile = null;
let currentMode = "image";

dateStamp.textContent = new Date().toISOString().slice(0, 10);

// --- Mode toggle (image upload vs typed description) ---
modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    modeButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;

    document.querySelectorAll(".input-mode").forEach((el) => el.classList.remove("active"));
    document.getElementById(`mode-${currentMode}`).classList.add("active");

    updateAnalyzeButtonState();
  });
});

function updateAnalyzeButtonState() {
  if (currentMode === "image") {
    analyzeBtn.disabled = !selectedFile;
  } else {
    analyzeBtn.disabled = descriptionInput.value.trim().length === 0;
  }
}

descriptionInput.addEventListener("input", updateAnalyzeButtonState);

// --- Dropzone interactions ---
dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) {
    handleFile(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});

function handleFile(file) {
  if (!file.type.startsWith("image/")) {
    setStatus("Please choose an image file.", "error");
    return;
  }
  selectedFile = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    preview.src = e.target.result;
    preview.hidden = false;
    hint.style.display = "none";
  };
  reader.readAsDataURL(file);
  updateAnalyzeButtonState();
  setStatus("");
}

function setStatus(msg, type = "") {
  statusEl.textContent = msg;
  statusEl.className = "status" + (type ? " " + type : "");
}

// --- Analyze pipeline ---
analyzeBtn.addEventListener("click", async () => {
  const visionModel = document.getElementById("visionModel").value.trim() || "moondream";
  const textModel = document.getElementById("textModel").value.trim() || "llama3.2";

  analyzeBtn.disabled = true;

  const formData = new FormData();

  if (currentMode === "image") {
    if (!selectedFile) return;
    formData.append("diagram", selectedFile);
    setStatus("Running Ollama vision pass, generating SQL, rendering diagram…");
  } else {
    const description = descriptionInput.value.trim();
    if (!description) return;
    formData.append("description", description);
    setStatus("Converting description to schema, generating SQL, rendering diagram…");
  }

  try {
    const res = await fetch(
      `/api/analyze?visionModel=${encodeURIComponent(visionModel)}&textModel=${encodeURIComponent(textModel)}`,
      { method: "POST", body: formData }
    );
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || data.error || "Pipeline failed");
    }

    renderResults(data);
    setStatus("Done.", "ok");
    revEl.textContent = data.jobId.slice(0, 8);
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    updateAnalyzeButtonState();
  }
});

function renderResults(data) {
  resultsPanel.hidden = false;

  document.getElementById("schemaOutput").textContent = JSON.stringify(data.schema, null, 2);
  document.getElementById("sqlOutput").textContent = data.sql;

  const diagramImg = document.getElementById("diagramImg");
  diagramImg.src = data.downloads.png + `?t=${Date.now()}`;

  document.getElementById("downloadPng").href = data.downloads.png;
  document.getElementById("downloadSvg").href = data.downloads.svg;
  document.getElementById("downloadSql").href = data.downloads.sql;

  resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

// --- Tabs ---
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});
