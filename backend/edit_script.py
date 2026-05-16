"""
edit_script.py — Step 4: Edit Script Extraction
COE 543/743 — Wikipedia Infobox Comparison Project
"""

import json
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ─────────────────────────────────────────────
#  XML helpers
# ─────────────────────────────────────────────

def _sanitize(text: str) -> str:
    """Remove XML 1.0 invalid control characters from text/attribute values."""
    result = []
    for ch in str(text):
        cp = ord(ch)
        if cp == 9 or cp == 10 or cp == 13 or cp >= 32:
            result.append(ch)
    return ''.join(result)


def _add(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Add a child element with text content."""
    child = ET.SubElement(parent, tag)
    child.text = text
    return child


# ─────────────────────────────────────────────
#  EditScript — core data class
# ─────────────────────────────────────────────

class EditScript:
    """
    Represents the formal edit script ES(T1, T2) between two document trees.

    IMPORTANT:
    The operation order must be preserved exactly as produced by the TED
    backtracking step. That order is the executable edit-script order.
    We therefore do NOT sort operations here.
    """

    def __init__(self,
                 country1: str,
                 country2: str,
                 ted_distance: float,
                 similarity: float,
                 operations: List[Dict]):
        self.country1 = country1
        self.country2 = country2
        self.ted_distance = ted_distance
        self.similarity = similarity
        self.generated_at = datetime.now(timezone.utc).isoformat()

        # Preserve original backtracking order exactly.
        self.operations = [dict(op) for op in operations]

    # ── Counts ────────────────────────────────────────────────────────

    @property
    def total_operations(self) -> int:
        return len(self.operations)

    @property
    def insert_count(self) -> int:
        return sum(1 for o in self.operations if o['op'] == 'insert')

    @property
    def delete_count(self) -> int:
        return sum(1 for o in self.operations if o['op'] == 'delete')

    @property
    def update_count(self) -> int:
        return sum(1 for o in self.operations if o['op'] == 'update')

    @property
    def match_count(self) -> int:
        return sum(1 for o in self.operations if o['op'] == 'match')

    @property
    def total_cost(self) -> float:
        return round(sum((o.get('cost') or 0) for o in self.operations), 4)

    # ── XML serialization ─────────────────────────────────────────────

    def to_xml(self) -> str:
        """Serialize the edit script to a pretty-printed XML string."""
        root = ET.Element('edit_script')

        # Metadata
        meta = ET.SubElement(root, 'metadata')
        _add(meta, 'country1', _sanitize(self.country1))
        _add(meta, 'country2', _sanitize(self.country2))
        _add(meta, 'ted_distance', str(self.ted_distance))
        _add(meta, 'similarity_score', f"{self.similarity:.4f}")
        _add(meta, 'total_operations', str(self.total_operations))
        _add(meta, 'inserts', str(self.insert_count))
        _add(meta, 'deletes', str(self.delete_count))
        _add(meta, 'updates', str(self.update_count))
        _add(meta, 'matches', str(self.match_count))
        _add(meta, 'total_cost', str(self.total_cost))
        _add(meta, 'generated_at', self.generated_at)
        _add(meta, 'algorithm', 'Chawathe TED (VLDB 1999)')
        _add(meta, 'ordering', 'execution_order_from_ted_backtracking')

        # Operations
        ops_elem = ET.SubElement(root, 'operations')

        for idx, op in enumerate(self.operations, start=1):
            op_elem = ET.SubElement(ops_elem, 'operation')
            op_elem.set('id', str(idx))  # execution order
            op_elem.set('type', op['op'])
            op_elem.set('cost', str(round(op.get('cost') or 0, 4)))

            # Source node (T1)
            src = ET.SubElement(op_elem, 'source')
            if op.get('id1') is not None:
                src.set('node_id', str(op['id1']))
                src.set('label', _sanitize(op.get('label1') or ''))
                src.set('value', _sanitize(op.get('value1') or ''))

            # Target node (T2)
            tgt = ET.SubElement(op_elem, 'target')
            if op.get('id2') is not None:
                tgt.set('node_id', str(op['id2']))
                tgt.set('label', _sanitize(op.get('label2') or ''))
                tgt.set('value', _sanitize(op.get('value2') or ''))

        raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        dom = xml.dom.minidom.parseString(raw)
        return dom.toprettyxml(indent='  ', encoding=None)

    # ── JSON serialization ────────────────────────────────────────────

    def to_dict(self) -> Dict:
        """Serialize the edit script to a JSON-serialisable dict."""
        return {
            'metadata': {
                'country1': self.country1,
                'country2': self.country2,
                'ted_distance': self.ted_distance,
                'similarity_score': self.similarity,
                'total_operations': self.total_operations,
                'inserts': self.insert_count,
                'deletes': self.delete_count,
                'updates': self.update_count,
                'matches': self.match_count,
                'total_cost': self.total_cost,
                'generated_at': self.generated_at,
                'algorithm': 'Chawathe TED (VLDB 1999)',
                'ordering': 'execution_order_from_ted_backtracking'
            },
            'operations': [
                {
                    'id': idx,  # execution order
                    'op': op['op'],
                    'cost': round(op.get('cost') or 0, 4),
                    'source': {
                        'node_id': op.get('id1'),
                        'label': op.get('label1'),
                        'value': op.get('value1'),
                        'parent_label': op.get('parent_label1'),
                        'field_label': op.get('field_label1')
                    },
                    'target': {
                        'node_id': op.get('id2'),
                        'label': op.get('label2'),
                        'value': op.get('value2'),
                        'parent_label': op.get('parent_label2'),
                        'field_label': op.get('field_label2')
                    }
                }
                for idx, op in enumerate(self.operations, start=1)
            ]
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the edit script to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    # ── File I/O ──────────────────────────────────────────────────────

    def save_xml(self, filepath: str) -> None:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_xml())
        print(f"[EditScript] Saved XML -> {filepath}")

    def save_json(self, filepath: str) -> None:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
        print(f"[EditScript] Saved JSON -> {filepath}")

    # ── Human-readable summary ────────────────────────────────────────

    def summary(self) -> str:
        lines = [
            f"Edit Script: ES({self.country1}, {self.country2})",
            f"  TED distance     : {self.ted_distance}",
            f"  Similarity       : {self.similarity:.1%}",
            f"  Total operations : {self.total_operations}",
            f"    Matches  : {self.match_count}  (cost = 0)",
            f"    Updates  : {self.update_count}",
            f"    Inserts  : {self.insert_count}",
            f"    Deletes  : {self.delete_count}",
            f"  Total cost       : {self.total_cost}",
            f"  Ordering         : execution order from TED backtracking",
        ]
        return '\n'.join(lines)


# ─────────────────────────────────────────────
#  EditScriptExtractor
# ─────────────────────────────────────────────

class EditScriptExtractor:
    """Extracts and formats the edit script from a TED comparison result."""

    def extract(self, comparison_result: Dict) -> EditScript:
        return EditScript(
            country1=comparison_result['country1'],
            country2=comparison_result['country2'],
            ted_distance=comparison_result['ted_distance'],
            similarity=comparison_result['similarity_score'],
            operations=comparison_result['edit_script']['operations']
        )

    def extract_and_save(self,
                         comparison_result: Dict,
                         xml_path: Optional[str] = None,
                         json_path: Optional[str] = None) -> EditScript:
        es = self.extract(comparison_result)
        if xml_path:
            es.save_xml(xml_path)
        if json_path:
            es.save_json(json_path)
        return es


# ─────────────────────────────────────────────
#  Quick demo
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    from ted_comparator import TEDComparator
    from database import WikipediaDatabase

    c1 = sys.argv[1] if len(sys.argv) > 1 else 'Lebanon'
    c2 = sys.argv[2] if len(sys.argv) > 2 else 'Switzerland'

    print(f"\nExtracting edit script: {c1} -> {c2}\n")

    db = WikipediaDatabase()
    comparator = TEDComparator()
    extractor = EditScriptExtractor()

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

    result = comparator.compare_countries(data1, data2)

    prefix = f"{c1.lower()}_{c2.lower()}"
    es = extractor.extract_and_save(
        result,
        xml_path=f"{prefix}_edit_script.xml",
        json_path=f"{prefix}_edit_script.json"
    )

    print(es.summary())
    print("\nFirst 5 operations:")
    for op in es.operations[:5]:
        print(
            f"  [{op['op'].upper():6}] "
            f"src=(id={op.get('id1')}, label={op.get('label1')!r}, "
            f"val={str(op.get('value1'))[:30]!r}) -> "
            f"tgt=(id={op.get('id2')}, label={op.get('label2')!r}, "
            f"val={str(op.get('value2'))[:30]!r})  cost={op.get('cost')}"
        )