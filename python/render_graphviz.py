#!/usr/bin/env python3
"""
render_graphviz.py
-------------------
Renders a clean, presentation-ready ER diagram (PNG + SVG) from the JSON
schema produced by interpret_er.py, using Graphviz.

Entities are drawn as HTML-like tables (name header + attribute rows,
with PK underlined and FK marked). Relationships are drawn as diamond
nodes connected to their entities, labeled with cardinality.

Usage:
    python3 render_graphviz.py <schema_json_path> <output_base_path>

    Produces <output_base_path>.png and <output_base_path>.svg
"""

import sys
import json
import argparse

from graphviz import Digraph


def attr_row(attr: dict) -> str:
    name = attr["name"]
    key = attr.get("key", "NONE")
    type_ = attr.get("type", "")
    label = name
    if key == "PK":
        label = f"<U><B>{name}</B></U>"
    elif key == "FK":
        label = f"<I>{name}</I> (FK)"
    return (
        f'<TR><TD ALIGN="LEFT">{label}</TD>'
        f'<TD ALIGN="LEFT"><FONT COLOR="#666666">{type_}</FONT></TD></TR>'
    )


def entity_html_label(entity: dict) -> str:
    rows = "".join(attr_row(a) for a in entity.get("attributes", []))
    return f"""<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6">
  <TR><TD COLSPAN="2" BGCOLOR="#2b6cb0"><FONT COLOR="white"><B>{entity["name"]}</B></FONT></TD></TR>
  {rows}
</TABLE>
>"""


def build_graph(schema: dict) -> Digraph:
    dot = Digraph("ER", format="png")
    dot.attr(
        rankdir="LR",
        bgcolor="white",
        fontname="Helvetica",
        splines="spline",
        nodesep="0.6",
        ranksep="0.9",
    )
    dot.attr("node", fontname="Helvetica", fontsize="11")
    dot.attr("edge", fontname="Helvetica", fontsize="10", color="#4a5568")

    # Entities
    for entity in schema.get("entities", []):
        dot.node(
            entity["name"],
            label=entity_html_label(entity),
            shape="plain",
        )

    # Relationships as diamond nodes
    for i, rel in enumerate(schema.get("relationships", [])):
        rel_id = f"rel_{i}_{rel.get('name', 'rel')}"
        dot.node(
            rel_id,
            label=rel.get("name", "relates_to"),
            shape="diamond",
            style="filled",
            fillcolor="#fefcbf",
            color="#d69e2e",
        )
        cardinality = rel.get("cardinality", "")
        entities = rel.get("entities", [])
        for idx, ent_name in enumerate(entities):
            edge_label = ""
            if cardinality and len(entities) == 2:
                parts = cardinality.split(":")
                if len(parts) == 2:
                    edge_label = parts[idx] if idx < len(parts) else ""
            dot.edge(ent_name, rel_id, label=edge_label, dir="none")

    return dot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("schema_path")
    parser.add_argument("output_base")
    args = parser.parse_args()

    with open(args.schema_path, "r") as f:
        schema = json.load(f)

    dot = build_graph(schema)

    # Render both PNG and SVG
    dot.format = "png"
    dot.render(args.output_base, cleanup=True)

    dot.format = "svg"
    dot.render(args.output_base, cleanup=True)

    print(f"Rendered {args.output_base}.png and {args.output_base}.svg")


if __name__ == "__main__":
    main()
