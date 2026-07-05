const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const preview = document.getElementById("preview");
const hint = document.querySelector(".dropzone__hint");
const analyzeBtn = document.getElementById("analyzeBtn");
const statusEl = document.getElementById("status");
const resultsPanel = document.getElementById("resultsPanel");
const revEl = document.getElementById("rev");
const dateStamp = document.getElementById("dateStamp");

let selectedFile = null;

dateStamp.textContent = new Date().toISOString().slice(0, 10);

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
  analyzeBtn.disabled = false;
  setStatus("");
}

function setStatus(msg, type = "") {
  statusEl.textContent = msg;
  statusEl.className = "status" + (type ? " " + type : "");
}

// --- Analyze pipeline ---
analyzeBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  const visionModel = document.getElementById("visionModel").value.trim() || "llava";
  const textModel = document.getElementById("textModel").value.trim() || "llama3";

  analyzeBtn.disabled = true;
  setStatus("Running Ollama vision pass, generating SQL, rendering diagram…");

  const formData = new FormData();
  formData.append("diagram", selectedFile);

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
    analyzeBtn.disabled = false;
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
