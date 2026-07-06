#!/usr/bin/env python3
"""
interpret_er.py
---------------
Turns an ER diagram into structured JSON via one of two input modes:

  1. IMAGE MODE: a photo/sketch of an ER diagram.
     -> A local Ollama vision model (default: moondream) describes it in
        plain English, then a local Ollama text model (default: llama3.2)
        converts that description into strict JSON.

  2. TEXT MODE: a plain-English description typed directly by the user
     (e.g. "A Student has student_id as primary key and a name. A Course
     has course_id as primary key and a title. Students enroll in many
     courses and each course can have many students.")
     -> Skips the vision step entirely and goes straight to JSON conversion.

Includes a one-time retry if the model fails to produce valid, non-empty
JSON on the first attempt, plus a robust brace-matching JSON extractor
(more reliable than a plain regex when models add stray text).

Usage:
    python3 interpret_er.py <image_path> [--model moondream] [--text-model llama3.2]
    python3 interpret_er.py --description "A Student has..." [--text-model llama3.2]

Prints the resulting JSON schema to stdout.
"""

import sys
import json
import base64
import argparse
import re
import io
import urllib.request
import urllib.error

from PIL import Image, ImageOps


VISION_PROMPT = """Look at this image of a hand-drawn or digital Entity-Relationship (ER) diagram.
Describe it in plain, detailed English so someone who cannot see the image could redraw it
EXACTLY, with nothing missing.

Work shape by shape, left to right, top to bottom:

1. First, count and list every entity box/rectangle, using its exact name.
2. For EACH entity, count how many attribute ovals/circles or attribute rows are
   connected to or inside it, then list every single one by name, in order - do
   not skip any, even ones that seem minor (like street, city, number, etc).
   Note which one looks underlined, bold, or otherwise marked as the primary key.
3. Note if any attribute oval is itself connected to other smaller ovals (a
   composite attribute, e.g. "Address" made up of "Street", "City", "Number") -
   describe that whole cluster and which entity it belongs to.
4. Describe every line or diamond connecting entities: which two things it
   connects, what the relationship is called (if labeled), and any cardinality
   marks you can see (like 1, N, M, crow's feet, or numbers/letters near the
   ends of the lines).

Before finishing, double-check: re-count the total number of ovals/circles/rows
you described and make sure that count matches what's actually drawn in the
image. Do not omit any attribute for the sake of brevity."""

JSON_CONVERSION_PROMPT_TEMPLATE = """Convert the following plain-English description of an
ER diagram into STRICT JSON only (no markdown fences, no commentary, no explanation) matching
exactly this shape:

{{
  "entities": [
    {{
      "name": "EntityName",
      "attributes": [
        {{"name": "attribute_name", "type": "INT|VARCHAR|DATE|BOOLEAN|FLOAT|TEXT", "key": "PK|FK|NONE"}}
      ]
    }}
  ],
  "relationships": [
    {{
      "name": "RelationshipName",
      "entities": ["EntityA", "EntityB"],
      "cardinality": "1:1|1:N|N:1|M:N",
      "attributes": []
    }}
  ]
}}

Rules:
- Include EVERY attribute mentioned in the description below - do not drop or
  summarize any of them for brevity, even if there are many.
- If the description mentions a composite attribute cluster (e.g. "Address"
  made up of "Street", "City", "Number"), flatten it: add each sub-part as its
  own attribute on the entity it belongs to (e.g. street, city, number),
  rather than creating a separate entity for it, unless the description
  clearly says it connects to multiple different entities (in which case it
  IS a real entity, not a composite attribute).
- Infer a reasonable SQL type per attribute if not stated.
- If no primary key is mentioned for an entity, infer the most likely one (commonly "<entity>_id").
- If cardinality isn't stated, make your best guess (default to "1:N").
- There must be at least one entity in the output. If the description truly
  describes no entities at all, return {{"entities": [], "relationships": []}}.
- Output ONLY the JSON object, nothing else - no preamble, no closing remarks.

Description to convert:
\"\"\"
{description}
\"\"\"
"""

# Used on retry, when the model's first attempt wasn't valid/usable JSON.
# NOTE: unlike JSON_CONVERSION_PROMPT_TEMPLATE, this string is NOT passed
# through .format(), so braces here must be single (not doubled/escaped).
JSON_RETRY_SUFFIX = """

IMPORTANT: Your previous response was not acceptable (either invalid JSON or
missing data). This time, respond with ONLY the raw JSON object - it must
start with { and end with }, with no words, labels, or markdown fences
before or after it."""


def image_to_base64(path: str) -> str:
    """
    Re-encode the image through Pillow into a clean, standard JPEG before
    base64-encoding it. This avoids 'Failed to load image or audio file'
    errors some Ollama vision models throw on PNGs with alpha channels,
    palette color modes, unusual ICC profiles, or corrupted metadata.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)  # respect phone-camera rotation
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Downscale very large images; big screenshots/photos can also
        # trip up some vision models or blow past request size limits.
        max_dim = 1600
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def call_ollama_generate(host: str, model: str, prompt: str, image_b64: str = None) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if image_b64:
        payload["images"] = [image_b64]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Ollama returned HTTP {e.code} for model '{model}'. "
            f"Server said: {detail}"
        )
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {host}. Is `ollama serve` running "
            f"and has `ollama pull {model}` been run? Original error: {e}"
        )


def find_balanced_json_object(text: str) -> str:
    """
    Scans for the first '{' and returns the substring up to its matching
    '}', counting nested braces. More robust than a greedy regex when the
    model adds explanatory text with its own stray braces before/after.
    """
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No '{' found in response", text, 0)

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    raise json.JSONDecodeError("Unbalanced braces in response", text, start)


def extract_json(text: str) -> dict:
    """Ollama sometimes wraps JSON in markdown fences or adds stray text."""
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text

    if not candidate.strip().startswith("{"):
        candidate = find_balanced_json_object(candidate)

    return json.loads(candidate)


def validate_schema(schema: dict) -> dict:
    schema.setdefault("entities", [])
    schema.setdefault("relationships", [])
    for entity in schema["entities"]:
        entity.setdefault("attributes", [])
        for attr in entity["attributes"]:
            attr.setdefault("type", "VARCHAR")
            attr.setdefault("key", "NONE")
    for rel in schema["relationships"]:
        rel.setdefault("attributes", [])
        rel.setdefault("cardinality", "1:N")
        rel.setdefault("entities", [])
    return schema


def convert_description_to_json(host: str, text_model: str, description: str) -> dict:
    """
    Sends the description to the text model and tries to get back valid,
    non-empty JSON. Retries once with a stricter reminder if the first
    attempt fails or comes back with zero entities (a common silent-failure
    mode for small local models).
    """
    conversion_prompt = JSON_CONVERSION_PROMPT_TEMPLATE.format(description=description)
    last_error = None
    last_raw = ""

    for attempt in range(2):
        prompt = conversion_prompt if attempt == 0 else conversion_prompt + JSON_RETRY_SUFFIX
        raw_response = call_ollama_generate(host, text_model, prompt)
        last_raw = raw_response
        try:
            schema = extract_json(raw_response)
            schema = validate_schema(schema)
        except json.JSONDecodeError as je:
            last_error = f"invalid JSON ({je})"
            continue

        if not schema["entities"]:
            last_error = "the model returned zero entities"
            continue

        return schema  # success

    raise RuntimeError(
        f"Text model '{text_model}' failed to produce a usable schema after 2 attempts "
        f"(last issue: {last_error}). Raw last response was: {last_raw[:500]!r}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path", nargs="?", default=None,
                        help="Path to an ER diagram image (omit if using --description)")
    parser.add_argument("--description", default=None,
                        help="Plain-English description of the ER diagram, as an alternative to an image")
    parser.add_argument("--model", default="moondream", help="Vision model (describes the image)")
    parser.add_argument("--text-model", default="llama3.2", help="Text model (converts description to JSON)")
    parser.add_argument("--host", default="http://localhost:11434")
    args = parser.parse_args()

    try:
        if not args.image_path and not args.description:
            raise RuntimeError("Provide either an image path or --description text.")

        if args.description:
            description = args.description.strip()
            if not description:
                raise RuntimeError("--description was provided but empty.")
        else:
            image_b64 = image_to_base64(args.image_path)
            description = call_ollama_generate(args.host, args.model, VISION_PROMPT, image_b64=image_b64)
            if not description.strip():
                raise RuntimeError(f"Vision model '{args.model}' returned an empty description.")

        schema = convert_description_to_json(args.host, args.text_model, description)
        print(json.dumps(schema, indent=2))

    except Exception as e:
        # Emit a minimal, still-valid JSON schema on failure so downstream
        # steps don't crash, plus the error goes to stderr for logging.
        print(f"ERROR: {e}", file=sys.stderr)
        print(json.dumps({"entities": [], "relationships": [], "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()