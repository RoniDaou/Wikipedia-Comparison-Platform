"""
tree_builder.py — Wikipedia infobox document preprocessing and tree construction.
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from database import WikipediaDatabase


# ─────────────────────────────────────────────
#  TreeNode
# ─────────────────────────────────────────────

class TreeNode:
    def __init__(self, label: str, node_type: str = 'element', value: str = None):
        self.label     = label
        self.node_type = node_type
        self.value     = value
        self.children: List['TreeNode'] = []
        self.parent:   Optional['TreeNode'] = None
        self.node_id:  Optional[int] = None

    def add_child(self, child: 'TreeNode') -> None:
        child.parent = self
        self.children.append(child)

    def field_label(self) -> Optional[str]:
        """
        Human-readable field label for diff reporting.
        - text node  -> parent label
        - element    -> own label
        """
        if self.node_type == 'text':
            return self.parent.label if self.parent else None
        return self.label

    def is_leaf(self) -> bool:
        return len(self.children) == 0
# ─────────────────────────────────────────────
#  DocumentTreeBuilder
# ─────────────────────────────────────────────

class DocumentTreeBuilder:

    # ── Build tree ─────────────────────────────────────────────────────

    def build_tree(self, country_data: Dict) -> TreeNode:
        root = TreeNode(label='country', node_type='element')

        root.add_child(
            self._make_element('country_name', country_data.get('country_name', ''))
        )

        if 'source_url' in country_data:
            root.add_child(
                self._make_element('source_url', country_data['source_url'])
            )

        fields: Dict[str, str] = country_data.get('fields', {})
        for field_name, field_value in fields.items():
            tag = self._normalize_tag(field_name)
            value_str = str(field_value).strip()

            if '\n' in value_str:
                node = self._build_hierarchical_node(tag, value_str)
            else:
                node = self._make_element(tag, value_str)

            root.add_child(node)

        self.assign_ids(root)
        return root

    # ── Internal builders ──────────────────────────────────────────────

    def _make_element(self, tag: str, text_value: str) -> TreeNode:
        element = TreeNode(label=tag, node_type='element')
        text    = TreeNode(label='#text', node_type='text', value=text_value)
        element.add_child(text)
        return element

    def _build_hierarchical_node(self, tag: str, value: str) -> TreeNode:
        parent = TreeNode(label=tag, node_type='element')
        lines  = [l for l in value.split('\n') if l.strip()]
        last_top_item = None

        for line in lines:
            depth   = self._get_depth(line)
            cleaned = self._clean_line(line)
            if not cleaned:
                continue

            if depth == 0:
                item = self._make_element('item', cleaned)
                parent.add_child(item)
                last_top_item = item
            else:
                sub = self._make_element('sub_item', cleaned)
                if last_top_item is not None:
                    last_top_item.add_child(sub)
                else:
                    parent.add_child(sub)

        if not parent.children:
            parent.add_child(TreeNode(label='#text', node_type='text', value=value.strip()))

        return parent

    # ── Line helpers ───────────────────────────────────────────────────

    def _get_depth(self, line: str) -> int:
        indent = len(line) - len(line.lstrip())
        if '├── ' in line or '└── ' in line:
            return max(1, indent // 4)
        return 0

    def _clean_line(self, line: str) -> str:
        cleaned = line
        for connector in ('├── ', '└── ', '│   ', '│'):
            cleaned = cleaned.replace(connector, '')
        return cleaned.strip()

    # ── Tag normalisation ──────────────────────────────────────────────

    def _normalize_tag(self, name: str) -> str:
        tag = name.lower().strip()
        tag = re.sub(r'[^a-z0-9]', '_', tag)
        tag = re.sub(r'_+', '_', tag)
        tag = tag.strip('_')
        if tag and tag[0].isdigit():
            tag = 'y' + tag
        tag = re.sub(r'^[^a-z]+', '', tag)
        return tag if tag else 'field'

    # ── Post-order IDs ─────────────────────────────────────────────────

    def assign_ids(self, root: TreeNode) -> int:
        counter = [0]

        def _postorder(node: TreeNode):
            for child in node.children:
                _postorder(child)
            counter[0] += 1
            node.node_id = counter[0]

        _postorder(root)
        return counter[0]

    # ── XML helpers ────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_xml(text: str) -> str:
        """Remove XML 1.0 invalid control characters."""
        result = []
        for ch in str(text):
            cp = ord(ch)
            if cp == 9 or cp == 10 or cp == 13 or cp >= 32:
                result.append(ch)
        return ''.join(result)

    @staticmethod
    def _esc(text: str) -> str:
        """Escape XML special characters."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

    # ── Export: XML ────────────────────────────────────────────────────

     # ── Export: XML ────────────────────────────────────────────────────

    def tree_to_xml(self, root: TreeNode) -> str:
        """
        Serialize the tree to valid XML while preserving:
          - child order
          - mixed content (#text + element children)
          - Unicode text

        Text nodes are emitted as XML text / tail text, not as <#text>.
        """
        root_elem = self._build_etree_element(root)
        xml_bytes = ET.tostring(
            root_elem,
            encoding='utf-8',
            xml_declaration=True,
            short_empty_elements=False
        )
        return xml_bytes.decode('utf-8')

    def _build_etree_element(self, node: TreeNode) -> ET.Element:
        """
        Convert one project TreeNode into a real ElementTree element.

        IMPORTANT:
        Text children are attached to .text / .tail so mixed-content
        nodes such as:
            item -> [#text("Christianity"), sub_item(...)]
        serialize correctly and in the right order.
        """
        if node.node_type == 'text':
            raise ValueError("Text nodes must be serialized through their parent element.")

        label = self._sanitize_xml(node.label)
        elem = ET.Element(label)

        # Rare fallback: an element node carrying its own direct value
        if node.value is not None and not node.children:
            elem.text = self._sanitize_xml(node.value)

        last_element_child = None

        for child in node.children:
            if child.node_type == 'text':
                text_value = self._sanitize_xml(child.value or '')
                if last_element_child is None:
                    elem.text = (elem.text or '') + text_value
                else:
                    last_element_child.tail = (last_element_child.tail or '') + text_value
            else:
                child_elem = self._build_etree_element(child)
                elem.append(child_elem)
                last_element_child = child_elem

        return elem

    def save_xml(self, root: TreeNode, filepath: str) -> None:
        xml_str = self.tree_to_xml(root)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(xml_str)
        print(f"[TreeBuilder] Saved XML -> {filepath}")

    def _xml_lines(self, node: TreeNode, lines: list, depth: int):
        """Recursively build XML lines without using minidom."""
        indent = '  ' * depth
        label  = self._sanitize_xml(node.label)

        if node.node_type == 'text':
            val = self._esc(self._sanitize_xml(node.value or ''))
            lines.append(f'{indent}<{label}>{val}</{label}>')
            return

        # Separate text children from element children
        text_val  = None
        elem_kids = []
        for child in node.children:
            if child.node_type == 'text':
                text_val = self._sanitize_xml(child.value or '')
            else:
                elem_kids.append(child)

        if not elem_kids:
            # Leaf or text-only element
            val = self._esc(text_val or '')
            lines.append(f'{indent}<{label}>{val}</{label}>')
        else:
            lines.append(f'{indent}<{label}>')
            for child in elem_kids:
                self._xml_lines(child, lines, depth + 1)
            lines.append(f'{indent}</{label}>')

    def save_xml(self, root: TreeNode, filepath: str) -> None:
        xml_str = self.tree_to_xml(root)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(xml_str)
        print(f"[TreeBuilder] Saved XML -> {filepath}")

    # ── Export: Dict / JSON ────────────────────────────────────────────

    def tree_to_dict(self, node: TreeNode) -> Dict:
        result: Dict = {
            'label':   node.label,
            'type':    node.node_type,
            'node_id': node.node_id,
        }
        if node.value is not None:
            result['value'] = node.value
        if node.children:
            result['children'] = [self.tree_to_dict(c) for c in node.children]
        return result

    # ── Debug ──────────────────────────────────────────────────────────

    def print_tree(self, node: TreeNode, _indent: int = 0, _last: bool = True) -> None:
        connector = '└── ' if _last else '├── '
        print(
            ('    ' * (_indent - 1) if _indent > 1 else '') +
            (connector if _indent > 0 else '') +
            f"[{node.node_type}] {node.label}" +
            (f" = {node.value!r}" if node.value else '') +
            (f"  (id={node.node_id})" if node.node_id else '')
        )
        for i, child in enumerate(node.children):
            self.print_tree(child, _indent + 1, i == len(node.children) - 1)

    # ── Statistics ─────────────────────────────────────────────────────

    def get_stats(self, root: TreeNode) -> Dict:
        stats = {
            'total_nodes':   0,
            'element_nodes': 0,
            'text_nodes':    0,
            'leaf_nodes':    0,
            'max_depth':     0,
            'country_name':  None,
        }

        def _traverse(node: TreeNode, depth: int):
            stats['total_nodes'] += 1
            stats['max_depth']    = max(stats['max_depth'], depth)

            if node.node_type == 'element':
                stats['element_nodes'] += 1
            elif node.node_type == 'text':
                stats['text_nodes'] += 1

            if node.is_leaf():
                stats['leaf_nodes'] += 1

            if node.label == 'country_name' and node.children:
                child = node.children[0]
                if child.node_type == 'text':
                    stats['country_name'] = child.value

            for child in node.children:
                _traverse(child, depth + 1)

        _traverse(root, 0)
        return stats


# ─────────────────────────────────────────────
#  Convenience function
# ─────────────────────────────────────────────

def build_tree_from_db(country_name: str,
                       db: WikipediaDatabase = None) -> Optional[TreeNode]:
    if db is None:
        db = WikipediaDatabase()
    country_data = db.get_country(country_name)
    if not country_data:
        print(f"[TreeBuilder] Country not found in DB: {country_name!r}")
        return None
    builder = DocumentTreeBuilder()
    return builder.build_tree(country_data)


# ─────────────────────────────────────────────
#  Quick demo
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    country = sys.argv[1] if len(sys.argv) > 1 else 'Lebanon'

    print(f"\n{'='*55}")
    print(f"  DocumentTreeBuilder — demo for: {country}")
    print(f"{'='*55}\n")

    db      = WikipediaDatabase()
    builder = DocumentTreeBuilder()

    data = db.get_country(country)
    if not data:
        print(f"'{country}' not found in database. Scrape it first.")
        sys.exit(1)

    root  = builder.build_tree(data)
    stats = builder.get_stats(root)

    print("Tree structure (first 3 levels shown via XML):\n")
    xml_str = builder.tree_to_xml(root)
    for line in xml_str.splitlines()[:40]:
        print(line)
    print("  ... (truncated)")

    print(f"\nTree statistics:")
    for k, v in stats.items():
        print(f"  {k:<16}: {v}")

    output_path = f"{country.lower().replace(' ', '_')}_tree.xml"
    builder.save_xml(root, output_path)
    print(f"\nFull XML saved to: {output_path}")