#!/usr/bin/env python3
"""
generate_sql.py
---------------
Takes the JSON schema produced by interpret_er.py and:
  1. Deterministically emits CREATE TABLE statements (reliable, no
     hallucination risk) including PK/FK constraints and junction
     tables for M:N relationships.
  2. Asks a local Ollama text model (default: llama3) to write a
     handful of useful sample SQL queries (JOINs, aggregates) against
     that exact schema, appended as commented extras.

Usage:
    python3 generate_sql.py <schema_json_path> [--model llama3] [--host http://localhost:11434]

Prints the final .sql content to stdout.
"""

import sys
import json
import argparse
import urllib.request
import urllib.error


SQL_TYPE_MAP = {
    "INT": "INTEGER",
    "INTEGER": "INTEGER",
    "VARCHAR": "VARCHAR(255)",
    "TEXT": "TEXT",
    "DATE": "DATE",
    "DATETIME": "DATETIME",
    "BOOLEAN": "BOOLEAN",
    "FLOAT": "FLOAT",
    "DECIMAL": "DECIMAL(10,2)",
}


def sql_type(t: str) -> str:
    return SQL_TYPE_MAP.get((t or "VARCHAR").upper(), "VARCHAR(255)")


def entity_pk(entity: dict) -> str:
    for attr in entity["attributes"]:
        if attr.get("key") == "PK":
            return attr["name"]
    # fallback: first attribute
    return entity["attributes"][0]["name"] if entity["attributes"] else f'{entity["name"].lower()}_id'


def build_create_tables(schema: dict) -> str:
    lines = ["-- Auto-generated schema from ER Diagram Interpreter", ""]
    entity_by_name = {e["name"]: e for e in schema["entities"]}

    # --- Entity tables ---
    for entity in schema["entities"]:
        name = entity["name"]
        cols = []
        pk_cols = []
        for attr in entity["attributes"]:
            col_def = f'  {attr["name"]} {sql_type(attr.get("type"))}'
            if attr.get("key") == "PK":
                pk_cols.append(attr["name"])
            cols.append(col_def)
        if pk_cols:
            cols.append(f'  PRIMARY KEY ({", ".join(pk_cols)})')
        lines.append(f"CREATE TABLE {name} (")
        lines.append(",\n".join(cols))
        lines.append(");")
        lines.append("")

    # --- Relationships ---
    for rel in schema.get("relationships", []):
        rel_entities = rel.get("entities", [])
        cardinality = rel.get("cardinality", "1:N")

        if cardinality == "M:N" and len(rel_entities) == 2:
            # Junction table
            e1, e2 = rel_entities
            if e1 not in entity_by_name or e2 not in entity_by_name:
                continue
            pk1 = entity_pk(entity_by_name[e1])
            pk2 = entity_pk(entity_by_name[e2])
            table_name = rel.get("name") or f"{e1}_{e2}"
            cols = [f"  {e1.lower()}_{pk1} INTEGER", f"  {e2.lower()}_{pk2} INTEGER"]
            for attr in rel.get("attributes", []):
                cols.append(f'  {attr["name"]} {sql_type(attr.get("type"))}')
            cols.append(f"  PRIMARY KEY ({e1.lower()}_{pk1}, {e2.lower()}_{pk2})")
            cols.append(f"  FOREIGN KEY ({e1.lower()}_{pk1}) REFERENCES {e1}({pk1})")
            cols.append(f"  FOREIGN KEY ({e2.lower()}_{pk2}) REFERENCES {e2}({pk2})")
            lines.append(f"CREATE TABLE {table_name} (")
            lines.append(",\n".join(cols))
            lines.append(");")
            lines.append("")
        elif len(rel_entities) == 2:
            # 1:N / N:1 / 1:1 -> add FK to the "many" side.
            # Heuristic: second listed entity gets the FK unless cardinality says otherwise.
            parent, child = rel_entities[0], rel_entities[1]
            if cardinality == "N:1":
                parent, child = child, parent
            if parent not in entity_by_name or child not in entity_by_name:
                continue
            parent_pk = entity_pk(entity_by_name[parent])
            fk_col = f"{parent.lower()}_{parent_pk}"
            lines.append(f"-- Relationship '{rel.get('name', '')}' ({cardinality}): "
                         f"add FK to {child}")
            lines.append(f"ALTER TABLE {child} ADD COLUMN {fk_col} INTEGER;")
            lines.append(f"ALTER TABLE {child} ADD FOREIGN KEY ({fk_col}) "
                         f"REFERENCES {parent}({parent_pk});")
            lines.append("")

    return "\n".join(lines)


def call_ollama_for_queries(host: str, model: str, schema: dict, ddl: str) -> str:
    prompt = f"""Given this SQL schema:

{ddl}

Write 5 useful example SQL queries a developer would run against this schema
(e.g. joins across relationships, aggregations, filtering).

STRICT RULE: Only reference tables and columns that literally appear in the
schema above. Do not invent, assume, or add any table or column that isn't
explicitly listed (no guessing at "name", "city", "state_id", etc. unless
they are actually declared above). If the schema is too limited for a
particular kind of query, write a simpler query that still only uses the
real columns, rather than inventing new ones.

Return ONLY SQL, each query preceded by a one-line "-- " comment explaining it.
No markdown fences."""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }
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
            return body.get("response", "").strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return f"-- (Sample queries unavailable: Ollama returned HTTP {e.code} for model '{model}': {detail})"
    except urllib.error.URLError as e:
        return f"-- (Sample queries unavailable: could not reach Ollama model '{model}' at {host}: {e})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("schema_path")
    parser.add_argument("--model", default="llama3.2")
    parser.add_argument("--host", default="http://localhost:11434")
    args = parser.parse_args()

    with open(args.schema_path, "r") as f:
        schema = json.load(f)

    ddl = build_create_tables(schema)
    sample_queries = call_ollama_for_queries(args.host, args.model, schema, ddl)

    output = ddl + "\n\n-- ==========================================\n"
    output += "-- Sample queries (generated by Ollama)\n"
    output += "-- ==========================================\n\n"
    output += sample_queries + "\n"

    print(output)


if __name__ == "__main__":
    main()
