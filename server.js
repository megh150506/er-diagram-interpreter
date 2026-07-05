/**
 * server.js
 * ---------
 * Express server that orchestrates the ER Diagram Interpreter pipeline:
 *   1. Accepts an uploaded ER diagram image (hand-drawn or digital).
 *   2. Calls python/interpret_er.py -> uses a local Ollama vision model
 *      (e.g. llava) to extract entities/attributes/relationships as JSON.
 *   3. Calls python/generate_sql.py -> deterministically builds CREATE TABLE
 *      SQL, then asks a local Ollama text model (e.g. llama3) to generate
 *      a few sample queries against that schema.
 *   4. Calls python/render_graphviz.py -> renders a clean, refined ER
 *      diagram (PNG + SVG) from the extracted JSON using Graphviz.
 *   5. Returns everything to the frontend, and exposes download routes
 *      for the SQL file and the refined image.
 */

const express = require("express");
const multer = require("multer");
const cors = require("cors");
const { execFile } = require("child_process");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");

const app = express();
const PORT = process.env.PORT || 4000;
const PYTHON_BIN = process.env.PYTHON_BIN || "python3";

const UPLOAD_DIR = path.join(__dirname, "uploads");
const OUTPUT_DIR = path.join(__dirname, "output");
[UPLOAD_DIR, OUTPUT_DIR].forEach((d) => fs.mkdirSync(d, { recursive: true }));

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));
app.use("/output", express.static(OUTPUT_DIR));

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOAD_DIR),
  filename: (_req, file, cb) => {
    const id = crypto.randomUUID();
    cb(null, `${id}${path.extname(file.originalname) || ".png"}`);
  },
});
const upload = multer({
  storage,
  limits: { fileSize: 15 * 1024 * 1024 }, // 15MB
  fileFilter: (_req, file, cb) => {
    if (!file.mimetype.startsWith("image/")) {
      return cb(new Error("Only image files are accepted"));
    }
    cb(null, true);
  },
});

/** Promisified wrapper around execFile for calling python scripts. */
function runPython(scriptName, args = []) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, "python", scriptName);
    execFile(
      PYTHON_BIN,
      [scriptPath, ...args],
      { maxBuffer: 1024 * 1024 * 50 },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error(stderr || error.message));
          return;
        }
        resolve(stdout.trim());
      }
    );
  });
}

/**
 * POST /api/analyze
 * Body: multipart/form-data, field "diagram" = image file
 * Optional query params: ?visionModel=llava&textModel=llama3
 */
app.post("/api/analyze", upload.single("diagram"), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No image uploaded (field name: diagram)" });
  }

  const jobId = crypto.randomUUID();
  const imagePath = req.file.path;
  const schemaPath = path.join(OUTPUT_DIR, `${jobId}.schema.json`);
  const sqlPath = path.join(OUTPUT_DIR, `${jobId}.sql`);
  const diagramBase = path.join(OUTPUT_DIR, `${jobId}.refined`);

  const visionModel = req.query.visionModel || "moondream";
  const textModel = req.query.textModel || "llama3.2";

  try {
    // 1. Interpret the raw image into structured JSON via a two-stage
    //    pipeline: vision model describes it, text model converts to JSON
    const schemaRaw = await runPython("interpret_er.py", [
      imagePath,
      "--model", visionModel,
      "--text-model", textModel,
    ]);
    fs.writeFileSync(schemaPath, schemaRaw);

    // 2. Generate SQL (deterministic CREATE TABLEs + Ollama sample queries)
    const sql = await runPython("generate_sql.py", [schemaPath, "--model", textModel]);
    fs.writeFileSync(sqlPath, sql);

    // 3. Render a refined ER diagram with Graphviz
    await runPython("render_graphviz.py", [schemaPath, diagramBase]);

    res.json({
      jobId,
      schema: JSON.parse(schemaRaw),
      sql,
      downloads: {
        sql: `/api/download/sql/${jobId}`,
        png: `/api/download/png/${jobId}`,
        svg: `/api/download/svg/${jobId}`,
      },
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Pipeline failed", detail: err.message });
  } finally {
    // Keep uploaded image only for debugging; remove if you don't need it
    // fs.unlink(imagePath, () => {});
  }
});

app.get("/api/download/sql/:jobId", (req, res) => {
  const file = path.join(OUTPUT_DIR, `${req.params.jobId}.sql`);
  if (!fs.existsSync(file)) return res.status(404).send("Not found");
  res.download(file, "schema.sql");
});

app.get("/api/download/png/:jobId", (req, res) => {
  const file = path.join(OUTPUT_DIR, `${req.params.jobId}.refined.png`);
  if (!fs.existsSync(file)) return res.status(404).send("Not found");
  res.download(file, "er_diagram_refined.png");
});

app.get("/api/download/svg/:jobId", (req, res) => {
  const file = path.join(OUTPUT_DIR, `${req.params.jobId}.refined.svg`);
  if (!fs.existsSync(file)) return res.status(404).send("Not found");
  res.download(file, "er_diagram_refined.svg");
});

app.get("/api/health", (_req, res) => res.json({ status: "ok" }));

app.listen(PORT, () => {
  console.log(`ER Diagram Interpreter running at http://localhost:${PORT}`);
});
