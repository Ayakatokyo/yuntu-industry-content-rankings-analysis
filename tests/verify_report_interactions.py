"""Offline integration checks against rendered HTML; no browser or network.

Usage: python tests/verify_report_interactions.py path/to/final-report.html output-dir
"""
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children, self.text = tag, dict(attrs), [], ""

    def all(self):
        yield self
        for child in self.children:
            yield from child.all()

    def content(self):
        return self.text + "".join(c.content() for c in self.children)


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.root = Node("document", [])
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"meta", "link", "img", "input", "br", "hr", "source", "wbr", "area", "base", "embed", "param", "track", "col"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        self.stack[-1].text += value


def verify(path, output):
    source = path.read_text()
    doc = Document(source)
    nodes = list(doc.root.all())
    ids = [n.attrs["id"] for n in nodes if "id" in n.attrs]
    assert len(ids) == len(set(ids)), "duplicate HTML IDs"
    for n in nodes:
        for target in n.attrs.get("aria-controls", "").split():
            assert target in ids, f"missing control target {target}"
        for key in ("src", "href"):
            target = n.attrs.get(key, "")
            if target.startswith("assets/") or target.endswith(".xlsx"):
                assert (path.parent / target).is_file(), f"missing resource {target}"
    tabs = [n.attrs for n in nodes if "data-script-brand-tab" in n.attrs]
    panels = [n.attrs for n in nodes if "data-script-brand-panel" in n.attrs]
    highlight_tabs = [n.attrs for n in nodes if "data-highlight-brand-tab" in n.attrs]
    assert len(tabs) == len(panels) == len(highlight_tabs) > 0, (
        "script and highlight brand tab/panel counts must match and be non-zero"
    )
    vectors = []
    for node in nodes:
        if "material-deep-panel" not in node.attrs.get("class", "").split():
            continue
        descendants = list(node.all())
        buttons = [n.attrs for n in descendants if "script-formula-item" in n.attrs.get("class", "").split()]
        spans = [{"attrs": n.attrs, "text": n.content()} for n in descendants if "data-script-evidence-ref" in n.attrs]
        scripts = [n for n in descendants if "script-text-body" in n.attrs.get("class", "").split()]
        if buttons:
            vectors.append({"id": node.attrs["id"], "buttons": buttons, "spans": spans,
                            "textLength": sum(len(n.content()) for n in scripts)})
    scripts = [n.content() for n in nodes if n.tag == "script" and n.attrs.get("type", "") not in {"application/json", "application/ld+json"}]
    payload = {"tabs": tabs, "panels": panels, "vectors": vectors, "scripts": scripts,
               "highlightTabs": highlight_tabs, "highlightPanels": [n.attrs for n in nodes if "data-highlight-brand-panel" in n.attrs]}
    output.mkdir(parents=True, exist_ok=True)
    payload_path = output / "dom-vectors.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False))
    result = subprocess.run(["node", str(Path(__file__).with_name("verify_report_interactions.cjs")), str(payload_path)], text=True, capture_output=True, check=True)
    print(result.stdout.strip())
    (output / "interactions.json").write_text(result.stdout)


if __name__ == "__main__":
    verify(Path(sys.argv[1]), Path(sys.argv[2]))
