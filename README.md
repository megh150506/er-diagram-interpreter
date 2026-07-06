ER Diagram Interpreter
Upload a hand-drawn (or digital) ER diagram → get back:
a structured JSON schema (entities, attributes, relationships)
a `.sql` file with `CREATE TABLE` statements + sample queries
a refined, redrawn ER diagram (`.png` and `.svg`) via Graphviz
Pipeline: Node.js (Express) orchestrates → Python scripts call a local
Ollama vision model to read the image and a text model to write sample
queries → Graphviz renders the clean diagram.
1. Prerequisites
Node.js 18+
Python 3.9+
Graphviz system binary (`dot` must be on your PATH)
macOS: `brew install graphviz`
Ubuntu/Debian: `sudo apt install graphviz`
Windows: install from graphviz.org and add `bin/` to PATH
Ollama installed and running (`ollama serve`)
Pull a vision-capable model: `ollama pull llava`
Pull a text model: `ollama pull llama3`
2. Install dependencies
```bash
# Node deps
npm install

# Python deps
pip install -r python/requirements.txt
```
3. Run
```bash
# make sure Ollama is running in another terminal
ollama serve

# start the server
npm start
```
Open http://localhost:4000 in your browser.
4. Usage
Drop in / select an ER diagram image.
(Optional) change the vision/text model names if you're using different
Ollama models (e.g. `bakllava`, `llama3.1`, `mistral`).
Click Interpret diagram.
Review the refined diagram, JSON schema, and SQL in the tabs.
Download any of the three outputs.
5. Project structure
```
er-diagram-interpreter/
├── server.js                  # Express server + pipeline orchestration
├── package.json
├── python/
│   ├── interpret_er.py        # image -> JSON schema (Ollama vision model)
│   ├── generate_sql.py        # JSON schema -> CREATE TABLEs + sample queries
│   ├── render_graphviz.py     # JSON schema -> refined PNG/SVG diagram
│   └── requirements.txt
├── public/                    # frontend (upload UI, tabs, downloads)
│   ├── index.html
│   ├── style.css
│   └── script.js
├── uploads/                   # incoming images (gitignored)
└── output/                    # generated schema/sql/diagram files (gitignored)
```
6. Notes / troubleshooting
If `interpret_er.py` can't reach Ollama, check `ollama serve` is running on
`http://localhost:11434` (default) — override with `--host` if it's remote.
If the vision model's JSON is malformed, `interpret_er.py` already strips
markdown fences and grabs the widest `{...}` block — if it still fails,
try a stronger vision model or re-photograph the diagram with better lighting.
`render_graphviz.py` requires the Graphviz system binary, not just the
Python package — `pip install graphviz` alone will not work.
To skip Ollama's SQL commentary pass and just get deterministic DDL,
you can call `generate_sql.py` directly and ignore the appended section.
