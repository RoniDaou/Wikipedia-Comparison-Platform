"""
patcher.py — Step 5: Document Tree Patching + Step 6: Post-Processing
COE 543/743 — Wikipedia Infobox Comparison Project

Current design note:
This patcher reconstructs the patched output using T2's structure when
the target tree is available. That fixes placement/orphaning issues in
the current architecture.

Important:
A fully standalone patcher from only (T1 + ES) would require the edit
script to store insertion placement metadata (e.g. parent / position).
That is a later fix. For now, this file fixes the concrete correctness
bugs in the existing reconstruction-based patcher.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Optional

from database import WikipediaDatabase
from tree_builder import TreeNode, DocumentTreeBuilder
from ted_comparator import TEDComparator
from edit_script import EditScript, EditScriptExtractor


# ─────────────────────────────────────────────
#  TreePatcher
# ─────────────────────────────────────────────

class TreePatcher:
    """
    Applies an edit script to T1 to produce T2.

    Primary mode:
        Reconstruct the result using T2's structure plus the edit-script
        mapping. This avoids orphaned nodes, duplicates, and bad insert
        placement in the current backend design.

    Fallback mode:
        If T2 is unavailable, apply only the operations that can be
        safely interpreted from T1 + ES alone (updates, deletes).
        Inserts are skipped because the current ES format does not store
        parent/index placement metadata.
    """

    def patch(self,
              source_root: TreeNode,
              edit_script: EditScript,
              source_tree2_root: Optional[TreeNode] = None) -> TreeNode:
        """
        Patch source_root using edit_script.

        Args:
            source_root       : Root of T1 (source tree)
            edit_script       : EditScript produced by TED + extraction
            source_tree2_root : Root of T2 when available

        Returns:
            Patched TreeNode root
        """
        if source_tree2_root is None:
            return self._fallback_patch(source_root, edit_script)

        # Build T1 lookup
        t1_id_map: Dict[int, TreeNode] = {}
        self._index(source_root, t1_id_map)

        # Build T2-operation lookup: t2_id -> operation
        op_map: Dict[int, Dict] = {}
        for op in edit_script.operations:
            t2_id = op.get('id2')
            if t2_id is not None:
                op_map[t2_id] = op

        # Reconstruct in exact T2 order/structure
        result = self._reconstruct(
            t2_node=source_tree2_root,
            t1_id_map=t1_id_map,
            op_map=op_map
        )

        if result is None:
            result = TreeNode(label='country', node_type='element')

        DocumentTreeBuilder().assign_ids(result)
        return result

    # ── Reconstruction ─────────────────────────────────────────────────

    def _reconstruct(self,
                     t2_node: TreeNode,
                     t1_id_map: Dict[int, TreeNode],
                     op_map: Dict[int, Dict]) -> Optional[TreeNode]:
        """
        Build one output node corresponding to t2_node, then recursively
        build its children in T2 order.
        """
        t2_id = t2_node.node_id
        op = op_map.get(t2_id)

        # Case 1: no explicit op, or explicit insert -> copy T2 node
        if op is None or op['op'] == 'insert':
            out_node = self._copy_shallow(t2_node)

        # Case 2: match/update -> start from T1 node when possible,
        # then force final structure/type to match T2
        else:
            t1_node = None
            t1_id = op.get('id1')
            if t1_id is not None:
                t1_node = t1_id_map.get(t1_id)

            if t1_node is not None:
                out_node = TreeNode(
                    label=t1_node.label,
                    node_type=t1_node.node_type,
                    value=t1_node.value
                )
            else:
                out_node = self._copy_shallow(t2_node)

            # Critical fix:
            # final structural type must match T2
            out_node.node_type = t2_node.node_type

            if op['op'] == 'update':
                if op.get('label2') is not None:
                    out_node.label = op['label2']
                else:
                    out_node.label = t2_node.label

                if op.get('value2') is not None:
                    out_node.value = op['value2']
                else:
                    out_node.value = t2_node.value
            else:
                # For matches, sync to T2 for exactness
                out_node.label = t2_node.label
                out_node.value = t2_node.value

        # Recurse using T2 child order
        for t2_child in t2_node.children:
            child_out = self._reconstruct(t2_child, t1_id_map, op_map)
            if child_out is not None:
                out_node.add_child(child_out)

        return out_node

    # ── Fallback patching (no T2 tree available) ──────────────────────

    def _fallback_patch(self,
                        source_root: TreeNode,
                        edit_script: EditScript) -> TreeNode:
        """
        Best-effort patching using only T1 + ES.

        Supported safely:
          - update
          - delete

        Not safely supported with current ES format:
          - insert placement

        So inserts are intentionally skipped here.
        """
        root = self._deep_copy(source_root)
        id_map: Dict[int, TreeNode] = {}
        self._index(root, id_map)

        # Apply operations in stored execution order
        for op in edit_script.operations:
            op_type = op.get('op')
            node_id = op.get('id1')

            node = id_map.get(node_id) if node_id is not None else None

            if op_type == 'delete':
                if node is None:
                    continue
                if node.parent is None:
                    # Do not delete the root in fallback mode
                    continue

                parent = node.parent
                parent.children = [c for c in parent.children if c is not node]
                self._unindex(node, id_map)

            elif op_type == 'update':
                if node is None:
                    continue

                if op.get('label2') is not None:
                    node.label = op['label2']
                    node.node_type = self._infer_node_type_from_label(
                        op['label2'],
                        fallback=node.node_type
                    )

                if op.get('value2') is not None:
                    node.value = op['value2']

            # match -> no change
            # insert -> skipped intentionally (no placement metadata)

        DocumentTreeBuilder().assign_ids(root)
        return root

    # ── Helpers ───────────────────────────────────────────────────────

    def _index(self, root: TreeNode, id_map: Dict[int, TreeNode]) -> None:
        """Populate id_map with all reachable nodes."""
        if root.node_id is not None:
            id_map[root.node_id] = root
        for child in root.children:
            self._index(child, id_map)

    def _unindex(self, root: TreeNode, id_map: Dict[int, TreeNode]) -> None:
        """Remove a subtree from id_map."""
        if root.node_id is not None and root.node_id in id_map:
            del id_map[root.node_id]
        for child in root.children:
            self._unindex(child, id_map)

    def _deep_copy(self, node: TreeNode) -> TreeNode:
        new_node = TreeNode(
            label=node.label,
            node_type=node.node_type,
            value=node.value
        )
        new_node.node_id = node.node_id
        for child in node.children:
            new_node.add_child(self._deep_copy(child))
        return new_node

    def _copy_shallow(self, node: TreeNode) -> TreeNode:
        """Copy one node without children."""
        return TreeNode(
            label=node.label,
            node_type=node.node_type,
            value=node.value
        )

    def _infer_node_type_from_label(self,
                                    label: Optional[str],
                                    fallback: str = 'element') -> str:
        """
        Infer node type from the label in this project tree model.
        Only '#text' is a text node; everything else is an element node.
        """
        if label == '#text':
            return 'text'
        return 'element' if fallback not in ('text', 'element') else (
            'text' if label == '#text' else 'element'
        )


# ─────────────────────────────────────────────
#  PostProcessor — Step 6
# ─────────────────────────────────────────────

class PostProcessor:
    """Converts patched tree back to XML, JSON, and infobox text."""

    def __init__(self):
        self.builder = DocumentTreeBuilder()

    def tree_to_xml(self, root: TreeNode) -> str:
        return self.builder.tree_to_xml(root)

    def tree_to_dict(self, root: TreeNode) -> Dict:
        return self.builder.tree_to_dict(root)

    def tree_to_infobox(self,
                        root: TreeNode,
                        country_name: str = None) -> str:
        country = country_name or self._get_country_name(root)
        lines = [f"== Infobox: {country} (Patched) =="]
        lines.append('{| class="infobox"')

        for child in root.children:
            if child.node_type != 'element':
                continue
            if child.label in ('country_name', 'source_url'):
                continue
            if child.label in ('item', 'sub_item'):
                continue

            value = self._extract_value(child)
            if not value:
                continue

            field = child.label.replace('_', ' ').title()
            lines.append(f"|-\n! {field}\n| {value}")

        lines.append("|}")
        return '\n'.join(lines)

    def tree_to_json_document(self,
                              root: TreeNode,
                              country_name: str = None) -> str:
        country_name = country_name or self._get_country_name(root)

        fields: Dict[str, str] = {}
        for child in root.children:
            if child.node_type != 'element':
                continue
            if child.label in ('country_name', 'source_url'):
                continue
            fields[child.label] = self._extract_value(child)

        doc = {
            'country_name': country_name,
            'fields': fields,
            'source': 'patched_tree',
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(doc, indent=2, ensure_ascii=False)

    def _get_country_name(self, root: TreeNode) -> str:
        for child in root.children:
            if child.label == 'country_name' and child.children:
                val = child.children[0].value
                if val and val.strip():
                    return val.strip()

        for child in root.children:
            if child.children and child.children[0].node_type == 'text':
                val = child.children[0].value or ''
                if 0 < len(val) < 60 and '%' not in val and '$' not in val:
                    if child.label in ('country_name', 'name'):
                        return val.strip()

        return 'Patched Country'

    def _extract_value(self, node: TreeNode) -> str:
        if not node.children:
            return ''

        if len(node.children) == 1 and node.children[0].node_type == 'text':
            return node.children[0].value or ''

        parts = []
        for child in node.children:
            if child.node_type == 'text':
                parts.append(child.value or '')
            elif child.label in ('item', 'sub_item'):
                val = self._extract_value(child)
                if val:
                    parts.append(val)

        return '\n'.join(parts)


# ─────────────────────────────────────────────
#  PatchingPipeline
# ─────────────────────────────────────────────

class PatchingPipeline:
    """Full pipeline: TED -> Edit Script -> Patch -> Post-process"""

    def __init__(self):
        self.builder = DocumentTreeBuilder()
        self.comparator = TEDComparator()
        self.extractor = EditScriptExtractor()
        self.patcher = TreePatcher()
        self.processor = PostProcessor()

    def run(self, country1_data: Dict, country2_data: Dict) -> Dict:
        # Build trees
        tree1 = self.builder.build_tree(country1_data)
        tree2 = self.builder.build_tree(country2_data)

        # Step 3: TED
        ted_result = self.comparator.compare_countries(
            country1_data, country2_data
        )

        # Step 4: Edit script
        es = self.extractor.extract(ted_result)

        # Step 5: Patch T1 -> T2
        patched_tree = self.patcher.patch(tree1, es, tree2)

        # Step 6: Post-process
        target_name = country2_data['country_name']
        return {
            'source_country': country1_data['country_name'],
            'target_country': target_name,
            'ted_distance': ted_result['ted_distance'],
            'similarity': ted_result['similarity_score'],
            'edit_script': es.to_dict(),
            'patched_tree': self.processor.tree_to_dict(patched_tree),
            'xml': self.processor.tree_to_xml(patched_tree),
            'json_doc': self.processor.tree_to_json_document(
                patched_tree, target_name
            ),
            'infobox': self.processor.tree_to_infobox(
                patched_tree, target_name
            ),
        }


# ─────────────────────────────────────────────
#  Demo
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    c1 = sys.argv[1] if len(sys.argv) > 1 else 'Lebanon'
    c2 = sys.argv[2] if len(sys.argv) > 2 else 'Switzerland'

    db = WikipediaDatabase()
    pipeline = PatchingPipeline()

    data1 = db.get_country(c1)
    data2 = db.get_country(c2)

    if not data1:
        print(f"'{c1}' not found.")
        sys.exit(1)
    if not data2:
        print(f"'{c2}' not found.")
        sys.exit(1)

    data1.pop('_id', None)
    data2.pop('_id', None)

    result = pipeline.run(data1, data2)
    print(f"TED: {result['ted_distance']}  Similarity: {result['similarity']:.1%}")
    print(result['infobox'])