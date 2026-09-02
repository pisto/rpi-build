#!/usr/bin/env python3
"""Sort a dtc-decompiled .dts file's node children and properties alphabetically
so that structurally-similar trees diff cleanly with `diff --no-index`.

Node order in a raw dtc dump reflects the order nodes appear in the FDT blob,
which differs between sources (mainline vs downstream vs firmware) even when
the trees are otherwise identical. Sorting children/properties by name at
every level removes that noise.
"""
import re
import sys


class Node:
    __slots__ = ("header", "name", "props", "children")

    def __init__(self, header):
        self.header = header  # e.g. "label: name@unit {" or "name {"
        m = re.search(r'(?:^|:\s*)([^\s:{]+)\s*\{\s*$', header.strip())
        self.name = m.group(1) if m else header
        self.props = []    # list of raw property lines (text, no indent)
        self.children = []  # list of Node


def parse(lines):
    root_header_idx = None
    header_lines = []
    i = 0
    n = len(lines)
    # Preamble: /dts-v1/;, /memreserve/ ..., blank lines, comments before root node
    while i < n:
        stripped = lines[i].strip()
        if stripped.endswith('{'):
            break
        header_lines.append(lines[i])
        i += 1

    def parse_node(i):
        header = lines[i].strip()
        node = Node(header)
        i += 1
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if stripped in ('};', '}; '):
                return node, i + 1
            if stripped.endswith('{'):
                child, i = parse_node(i)
                node.children.append(child)
                continue
            if stripped == '':
                i += 1
                continue
            node.props.append(stripped)
            i += 1
        return node, i

    root, i = parse_node(i)
    trailer_lines = lines[i:]
    return header_lines, root, trailer_lines


def prop_key(p):
    m = re.match(r'([^\s=;]+)', p)
    return m.group(1) if m else p


def node_key(node):
    return node.name


def sort_node(node):
    node.props.sort(key=prop_key)
    for c in node.children:
        sort_node(c)
    node.children.sort(key=node_key)


def render(node, depth, out):
    indent = '\t' * depth
    out.append(f"{indent}{node.header}")
    for p in node.props:
        out.append(f"{indent}\t{p}")
    for c in node.children:
        render(c, depth + 1, out)
    out.append(f"{indent}}};")


def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <in.dts> <out.dts>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        lines = f.readlines()
    lines = [l.rstrip('\n') for l in lines]
    header_lines, root, trailer_lines = parse(lines)
    sort_node(root)
    out = list(header_lines)
    render(root, 0, out)
    out.extend(trailer_lines)
    with open(sys.argv[2], 'w') as f:
        f.write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
