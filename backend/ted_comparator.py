"""
ted_comparator.py — Tree Edit Distance (TED) with Tokenization & Optimal List Matching
COE 543/743 — Wikipedia Infobox Comparison Project

Implements Tree Edit Distance with:
1. Field tokenization (Parentheses, Brackets, Underscore)
2. Similarity-based cost (0.0-0.5 for content differences)
3. Optimal item reordering based on cross-tree fuzzy matching
4. Debug output to see what's happening
"""

from typing import Dict, List, Tuple, Optional
from tree_builder import TreeNode, DocumentTreeBuilder, WikipediaDatabase
from field_tokenizer import FieldTokenizer, TokenizedField
from difflib import SequenceMatcher
from list_item_matcher import ListItemMatcher


# ─────────────────────────────────────────────
#  LD-Pair representation with tokenization
# ─────────────────────────────────────────────

class LDPair:
    """A single element in the LD-pair string representing one tree node."""
    def __init__(self, label: str, depth: int,
                 value: Optional[str], node: TreeNode,
                 tokenized: Optional[TokenizedField] = None):
        self.label = label
        self.depth = depth
        self.value = value
        self.node  = node
        self.node_type = node.node_type
        self.tokenized = tokenized

    def __repr__(self):
        token_info = ""
        if self.tokenized and self.tokenized.parameters:
            token_info = f", base={self.tokenized.base_name!r}, params={self.tokenized.parameters}"
        return f"LD({self.label!r}, d={self.depth}{token_info})"


# ─────────────────────────────────────────────
#  Global tokenizer instance
# ─────────────────────────────────────────────

_TOKENIZER = FieldTokenizer()


# ─────────────────────────────────────────────
#  Item Matcher - Fuzzy Similarity
# ─────────────────────────────────────────────

class ItemMatcher:
    """Fuzzy matcher for list items."""

    @staticmethod
    def similarity(text1: str, text2: str) -> float:
        """Compute similarity between two items (0.0 to 1.0)."""
        return SequenceMatcher(None, text1 or '', text2 or '').ratio()

    @staticmethod
    def greedy_matching(items1: List[str], items2: List[str],
                       threshold: float = 0.2) -> Dict[int, Tuple[int, float]]:
        """Greedy bipartite matching."""
        matchings = {}
        used = set()
        
        for i, item1 in enumerate(items1):
            best_j = None
            best_sim = threshold
            
            for j, item2 in enumerate(items2):
                if j not in used:
                    sim = ItemMatcher.similarity(item1, item2)
                    if sim > best_sim:
                        best_sim = sim
                        best_j = j
            
            if best_j is not None:
                matchings[i] = (best_j, best_sim)
                used.add(best_j)
        
        return matchings


# ─────────────────────────────────────────────
#  Optimal Item Reordering
# ─────────────────────────────────────────────

def reorder_items_optimally(root1: TreeNode, root2: TreeNode, debug: bool = True) -> None:
    """
    Reorder items using COST MATRIX for optimal matching.
    """
    matcher_util = ListItemMatcher()
    
    def _get_text_value(node: TreeNode) -> Optional[str]:
        """Get text value from node's text child."""
        if node.children and node.children[0].node_type == 'text':
            return node.children[0].value
        return None
    
    def _reorder_field(field1: TreeNode, field2: TreeNode, field_name: str):
        """Reorder items using cost matrix."""
        items1 = [c for c in field1.children if c.label in ['item', 'sub_item']]
        items2 = [c for c in field2.children if c.label in ['item', 'sub_item']]
        
        if len(items1) <= 1 or len(items2) <= 1:
            return
        
        # Prepare data for cost matrix
        items_a = [(item.label, _get_text_value(item)) for item in items1]
        items_b = [(item.label, _get_text_value(item)) for item in items2]
        
        # Build cost matrix using tokenization + similarity
        cost_matrix = matcher_util.build_cost_matrix(items_a, items_b)
        
        if debug:
            print(f"\n🔄 REORDERING FIELD: {field_name}")
            matcher_util.print_cost_matrix(cost_matrix, items_a, items_b)
        
        # Find optimal matching
        matches = matcher_util.optimal_assignment(cost_matrix)
        
        if debug:
            matcher_util.print_matches(matches, items_a, items_b)
        
        # Reorder based on matches
        matched_in_1 = set()
        matched_in_2 = set()
        
        for i, j, cost in matches:
            matched_in_1.add(i)
            matched_in_2.add(j)
        
        # Build new ordering
        new_items1 = [items1[i] for i, j, cost in matches]
        for i in range(len(items1)):
            if i not in matched_in_1:
                new_items1.append(items1[i])
        
        new_items2 = [items2[j] for i, j, cost in matches]
        for j in range(len(items2)):
            if j not in matched_in_2:
                new_items2.append(items2[j])
        
        # Replace children
        non_items1 = [c for c in field1.children if c.label not in ['item', 'sub_item']]
        non_items2 = [c for c in field2.children if c.label not in ['item', 'sub_item']]
        
        field1.children = non_items1 + new_items1
        field2.children = non_items2 + new_items2
    
    def _traverse(node1: TreeNode, node2: TreeNode):
        """Recursively find and reorder matching fields."""
        if node1.node_type != 'element' or node2.node_type != 'element':
            return
        
        children1_by_label = {c.label: c for c in node1.children}
        children2_by_label = {c.label: c for c in node2.children}
        
        for label in children1_by_label:
            if label in children2_by_label:
                child1 = children1_by_label[label]
                child2 = children2_by_label[label]
                
                items1 = [c for c in child1.children if c.label in ['item', 'sub_item']]
                items2 = [c for c in child2.children if c.label in ['item', 'sub_item']]
                
                if items1 and items2:
                    _reorder_field(child1, child2, label)
                
                _traverse(child1, child2)
    
    _traverse(root1, root2)

def tree_to_ld_string(root: TreeNode) -> List[LDPair]:
    """Convert tree to LD-pair string via pre-order DFS with tokenization."""
    result: List[LDPair] = []

    def _preorder(node: TreeNode, depth: int):
        # ✅ Tokenize field labels for parameter-aware matching
        tokenized = _TOKENIZER.tokenize(node.label) if node.node_type == 'element' else None
        result.append(LDPair(node.label, depth, node.value, node, tokenized))
        for child in node.children:
            _preorder(child, depth + 1)

    _preorder(root, 0)
    return result


# ─────────────────────────────────────────────
#  Cost functions
# ─────────────────────────────────────────────

def cost_delete(pair: LDPair) -> float:
    """Cost of deleting a node."""
    # ✅ Don't count empty text nodes (from list items)
    if pair.node_type == 'text' and (not pair.value or str(pair.value).strip() == ''):
        return 0.0
    if pair.label in ['item', 'sub_item'] and (not pair.value or str(pair.value).strip() == ''):
        return 0.0
    return 1.0


def cost_insert(pair: LDPair) -> float:
    """Cost of inserting a node."""
    # ✅ Don't count empty text nodes (from list items)
    if pair.node_type == 'text' and (not pair.value or str(pair.value).strip() == ''):
        return 0.0
    if pair.label in ['item', 'sub_item'] and (not pair.value or str(pair.value).strip() == ''):
        return 0.0
    return 1.0


def cost_update(p1: LDPair, p2: LDPair) -> float:
    """
    Cost of updating p1 to match p2.
    ✅ All differences use similarity-based cost (0.0-1.0)
    ✅ Tokenization-aware for field names
    """

    # Depth constraint
    if p1.depth != p2.depth:
        return float('inf')

    # ════════════════════════════════════════════════════════════════
    # Tokenization-aware comparison (field LABELS with parameters)
    # ════════════════════════════════════════════════════════════════
    
    if p1.tokenized is not None and p2.tokenized is not None:
        # Both are tokenizable field-level element nodes
        
        # DIFFERENT BASE NAMES → compute similarity on base names
        if p1.tokenized.base_name != p2.tokenized.base_name:
            similarity = SequenceMatcher(None, 
                                       p1.tokenized.base_name, 
                                       p2.tokenized.base_name).ratio()
            return 1.0 * (1.0 - similarity)
        
        # SAME BASE NAME → compute parameter similarity
        param1_str = ','.join(p1.tokenized.parameters)
        param2_str = ','.join(p2.tokenized.parameters)
        
        # Identical parameters → perfect match
        if param1_str == param2_str:
            return 0.0
        
        # Different parameters → compute similarity
        similarity = SequenceMatcher(None, param1_str, param2_str).ratio()
        return 1.0 * (1.0 - similarity)

    # ════════════════════════════════════════════════════════════════
    # Label mismatch → compute similarity
    # ════════════════════════════════════════════════════════════════
    
    if p1.label != p2.label:
        sim = SequenceMatcher(None, p1.label, p2.label).ratio()
        return 1.0 * (1.0 - sim)

    # ════════════════════════════════════════════════════════════════
    # Label match → check values
    # ════════════════════════════════════════════════════════════════
    
    v1 = p1.value or ''
    v2 = p2.value or ''
    
    if v1 == v2:
        return 0.0
    
    # Different values → compute similarity
    sim = SequenceMatcher(None, v1, v2).ratio()
    return 1.0 * (1.0 - sim)



# ─────────────────────────────────────────────
#  Field-level reordering (fixes cross-field mismatches)
# ─────────────────────────────────────────────

def _field_similarity(label1: str, label2: str) -> float:
    """
    Similarity between two field labels using tokenization.

    Rules (in order):
    1. Identical labels            → 1.0  (perfect match)
    2. Same base AND same suffix   → 0.95 (e.g. total_2 ↔ total_2)
    3. Same base, different suffix → 0.50 (e.g. total ↔ total_2 — penalised
                                           so the DP prefers insert/delete over
                                           cross-matching numeric siblings)
    4. Different base              → character-level ratio on base names
    """
    if label1 == label2:
        return 1.0

    t1 = _TOKENIZER.tokenize(label1)
    t2 = _TOKENIZER.tokenize(label2)

    if t1.base_name == t2.base_name:
        # Same base — compare numeric suffix (the parameter part)
        # e.g. total vs total_2 have params [] vs ['2']
        p1 = '_'.join(t1.parameters)
        p2 = '_'.join(t2.parameters)
        if p1 == p2:
            return 0.95   # same base + same suffix → strong match
        else:
            return 0.50   # same base but different suffix → penalise heavily
                          # so total↔total_2 is never preferred over insert/delete

    return SequenceMatcher(None, t1.base_name, t2.base_name).ratio()


def reorder_fields_optimally(root1: TreeNode, root2: TreeNode) -> None:
    """
    Reorder the top-level field children of root1 and root2 so that
    semantically matching fields are aligned before the DP runs.

    This prevents Chawathe's positional string matching from pairing
    unrelated fields (e.g. Lebanon's 'capital' against Switzerland's
    'german_name') simply because they sit at the same index.

    Algorithm (bipartite optimal assignment on label similarity):
    1. Build an N×M cost matrix where cost[i][j] = 1 - sim(label_i, label_j)
    2. Run scipy linear_sum_assignment (greedy fallback if unavailable)
    3. Reorder root1's children so matched pairs appear in the same position
       Unmatched children from either tree are appended at the end.

    Only element children at depth=1 (the actual infobox fields) are touched.
    Text nodes and the country_name / source_url nodes are left in place.
    """
    # Collect reorderable field children (skip country_name, source_url, text nodes)
    SKIP = {'country_name', 'source_url', '#text'}

    fields1 = [c for c in root1.children if c.node_type == 'element' and c.label not in SKIP]
    fields2 = [c for c in root2.children if c.node_type == 'element' and c.label not in SKIP]

    n, m = len(fields1), len(fields2)
    if n == 0 or m == 0:
        return

    # Build cost matrix
    cost = [[1.0 - _field_similarity(fields1[i].label, fields2[j].label)
             for j in range(m)] for i in range(n)]

    # Optimal assignment
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        cost_np = np.array(cost)
        row_ind, col_ind = linear_sum_assignment(cost_np)
        matches = list(zip(row_ind.tolist(), col_ind.tolist()))
    except ImportError:
        # Greedy fallback
        used_j = set()
        matches = []
        for i in range(n):
            best_j, best_cost = None, float('inf')
            for j in range(m):
                if j not in used_j and cost[i][j] < best_cost:
                    best_cost = cost[i][j]
                    best_j = j
            if best_j is not None:
                matches.append((i, best_j))
                used_j.add(best_j)

    # Only keep matches where similarity is strong enough (> 0.5)
    # This prevents weakly-related fields from being paired; they will
    # be handled as insert+delete which is more accurate.
    matches = [(i, j) for i, j in matches if (1.0 - cost[i][j]) > 0.5]

    matched1 = {i for i, j in matches}
    matched2 = {j for i, j in matches}

    # Build reordered lists
    new_fields1 = [fields1[i] for i, j in matches]
    new_fields2 = [fields2[j] for i, j in matches]

    # Append unmatched — preserving original relative order
    for i, f in enumerate(fields1):
        if i not in matched1:
            new_fields1.append(f)
    for j, f in enumerate(fields2):
        if j not in matched2:
            new_fields2.append(f)

    # Splice back into root children, keeping non-field nodes in place
    def _rebuild(root, original_fields, new_fields):
        new_children = []
        field_iter = iter(new_fields)
        original_field_set = set(id(f) for f in original_fields)
        for child in root.children:
            if id(child) in original_field_set:
                new_children.append(next(field_iter))
            else:
                new_children.append(child)
        root.children = new_children

    _rebuild(root1, fields1, new_fields1)
    _rebuild(root2, fields2, new_fields2)


# ─────────────────────────────────────────────
#  Chawathe TED
# ─────────────────────────────────────────────

def chawathe_ted(root1: TreeNode, root2: TreeNode, debug: bool = True) -> Tuple[float, List[Dict]]:
    """Compute Tree Edit Distance with optimal reordering and tokenization."""
    
    if debug:
        print("\n" + "="*70)
        print("🚀 STARTING CHAWATHE TED WITH OPTIMAL REORDERING + TOKENIZATION")
        print("="*70)
    
    # ✅ STEP 1: Reorder top-level FIELDS so matching fields align positionally
    reorder_fields_optimally(root1, root2)

    # ✅ STEP 2: Reorder list ITEMS within already-aligned matching fields
    reorder_items_optimally(root1, root2, debug=debug)
    
    # Convert to LD-pairs (with tokenization)
    s1 = tree_to_ld_string(root1)
    s2 = tree_to_ld_string(root2)

    n = len(s1)
    m = len(s2)

    # Wagner & Fisher DP
    D = [[0.0] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        D[i][0] = D[i-1][0] + cost_delete(s1[i-1])
    for j in range(1, m + 1):
        D[0][j] = D[0][j-1] + cost_insert(s2[j-1])

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c_del   = D[i-1][j]   + cost_delete(s1[i-1])
            c_ins   = D[i][j-1]   + cost_insert(s2[j-1])
            c_upd   = D[i-1][j-1] + cost_update(s1[i-1], s2[j-1])
            D[i][j] = min(c_del, c_ins, c_upd)

    distance = D[n][m]
    operations = _backtrack(D, s1, s2)

    if debug:
        print(f"\n📊 TED DISTANCE: {distance}")
        print("="*70 + "\n")

    return round(distance, 4), operations


def _backtrack(D: List[List[float]], s1: List[LDPair], s2: List[LDPair]) -> List[Dict]:
    """Backtrack to recover edit script."""
    ops = []
    i = len(s1)
    j = len(s2)
    EPS = 1e-6
    used_t1 = set()
    used_t2 = set()

    while i > 0 or j > 0:
        if i > 0 and j > 0:
            p1, p2 = s1[i-1], s2[j-1]
            c_upd = cost_update(p1, p2)
            c_del = cost_delete(p1)
            c_ins = cost_insert(p2)

            if (p1.node.node_id not in used_t1 and
                p2.node.node_id not in used_t2 and
                abs(D[i][j] - (D[i-1][j-1] + c_upd)) < EPS):
                
                op_type = 'match' if abs(c_upd) < EPS else 'update'
                ops.append(_make_op(op_type, p1, p2, c_upd))
                used_t1.add(p1.node.node_id)
                used_t2.add(p2.node.node_id)
                i -= 1
                j -= 1

            elif abs(D[i][j] - (D[i-1][j] + c_del)) < EPS:
                if p1.node.node_id not in used_t1:
                    ops.append(_make_op('delete', p1, None, c_del))
                    used_t1.add(p1.node.node_id)
                i -= 1

            else:
                if p2.node.node_id not in used_t2:
                    ops.append(_make_op('insert', None, p2, c_ins))
                    used_t2.add(p2.node.node_id)
                j -= 1

        elif i > 0:
            p1 = s1[i-1]
            if p1.node.node_id not in used_t1:
                ops.append(_make_op('delete', p1, None, cost_delete(p1)))
                used_t1.add(p1.node.node_id)
            i -= 1

        else:
            p2 = s2[j-1]
            if p2.node.node_id not in used_t2:
                ops.append(_make_op('insert', None, p2, c_ins))
                used_t2.add(p2.node.node_id)
            j -= 1

    mapped_t2 = {op['id2'] for op in ops if op.get('id2')}
    for p2 in s2:
        if p2.node.node_id not in mapped_t2:
            ops.append(_make_op('insert', None, p2, cost_insert(p2)))

    ops.reverse()
    return ops


def _parent_label(pair: Optional[LDPair]) -> Optional[str]:
    if not pair or not pair.node or not pair.node.parent:
        return None
    return pair.node.parent.label


def _field_label(pair: Optional[LDPair]) -> Optional[str]:
    if not pair or not pair.node:
        return None
    return pair.node.field_label()


def _make_op(op_type: str, p1: Optional[LDPair], p2: Optional[LDPair], cost: float) -> Dict:
    """Build operation dictionary with tokenization info."""
    op_dict = {
        'op':            op_type,
        'id1':           p1.node.node_id if p1 else None,
        'id2':           p2.node.node_id if p2 else None,
        'label1':        p1.label if p1 else None,
        'label2':        p2.label if p2 else None,
        'value1':        p1.value if p1 else None,
        'value2':        p2.value if p2 else None,
        'parent_label1': _parent_label(p1),
        'parent_label2': _parent_label(p2),
        'field_label1':  _field_label(p1),
        'field_label2':  _field_label(p2),
        'cost':          round(cost, 4),
    }

    # ✅ Add tokenization info
    if p1 and p1.tokenized:
        op_dict['token1_base'] = p1.tokenized.base_name
        op_dict['token1_params'] = p1.tokenized.parameters
        op_dict['token1_type'] = p1.tokenized.tokenization_type

    if p2 and p2.tokenized:
        op_dict['token2_base'] = p2.tokenized.base_name
        op_dict['token2_params'] = p2.tokenized.parameters
        op_dict['token2_type'] = p2.tokenized.tokenization_type

    return op_dict


# ─────────────────────────────────────────────
#  TEDComparator
# ─────────────────────────────────────────────

class TEDComparator:
    """Compares two country infobox documents."""

    def __init__(self):
        self.builder = DocumentTreeBuilder()

    def compare_countries(self, country1_data: Dict, country2_data: Dict) -> Dict:
        """Full TED-based comparison."""
        tree1 = self.builder.build_tree(country1_data)
        tree2 = self.builder.build_tree(country2_data)

        stats1 = self.builder.get_stats(tree1)
        stats2 = self.builder.get_stats(tree2)

        size1 = stats1['total_nodes']
        size2 = stats2['total_nodes']

        # Run Chawathe TED with debug output
        distance, operations = chawathe_ted(tree1, tree2, debug=True)

        # Formula 2 from Chawathe (slide 43): Sim = 1 - TED / (|A| + |B|)
        # |A|+|B| is the max possible distance (delete all of A, insert all of B)
        total_size = max(size1 + size2, 1)
        similarity = max(0.0, 1.0 - (distance / total_size))

        inserts = [o for o in operations if o['op'] == 'insert']
        deletes = [o for o in operations if o['op'] == 'delete']
        updates = [o for o in operations if o['op'] == 'update']
        matches = [o for o in operations if o['op'] == 'match']

        fields1 = set(country1_data.get('fields', {}).keys())
        fields2 = set(country2_data.get('fields', {}).keys())

        return {
            'country1':         country1_data['country_name'],
            'country2':         country2_data['country_name'],
            'tree1_size':       size1,
            'tree2_size':       size2,
            'ted_distance':     round(distance, 4),
            'similarity_score': round(similarity, 4),
            'max_size':         size1 + size2,
            'common_fields':    len(fields1 & fields2),
            'unique_to_country1': len(fields1 - fields2),
            'unique_to_country2': len(fields2 - fields1),
            'fields_unique_to_country1': sorted(fields1 - fields2),
            'fields_unique_to_country2': sorted(fields2 - fields1),
            'edit_script': {
                'total_operations': len(operations),
                'inserts':          len(inserts),
                'deletes':          len(deletes),
                'updates':          len(updates),
                'matches':          len(matches),
                'operations':       self._serialize_operations(operations)
            },
            'tree1_stats': stats1,
            'tree2_stats': stats2,
        }

    def _serialize_operations(self, operations: List[Dict]) -> List[Dict]:
        """Serialize operations for JSON."""
        result = []
        for op in operations:
            op_dict = {
                'op': op['op'],
                'label1': op.get('label1'),
                'label2': op.get('label2'),
                'value1': op.get('value1'),
                'value2': op.get('value2'),
                'id1': op.get('id1'),
                'id2': op.get('id2'),
                'parent_label1': op.get('parent_label1'),
                'parent_label2': op.get('parent_label2'),
                'field_label1': op.get('field_label1'),
                'field_label2': op.get('field_label2'),
                'cost': round(op['cost'], 4)
            }
            
            # ✅ Include tokenization info
            if 'token1_base' in op:
                op_dict['token1'] = {
                    'base': op['token1_base'],
                    'params': op['token1_params'],
                    'type': op['token1_type']
                }
            if 'token2_base' in op:
                op_dict['token2'] = {
                    'base': op['token2_base'],
                    'params': op['token2_params'],
                    'type': op['token2_type']
                }

            result.append(op_dict)
        return result

    def generate_report(self, result: Dict) -> str:
        """Generate human-readable report."""
        c1 = result['country1']
        c2 = result['country2']
        sim = result['similarity_score']
        ted = result['ted_distance']
        es = result['edit_script']

        lines = [
            f"{'='*55}",
            f"  TED Comparison: {c1} vs {c2}",
            f"{'='*55}\n",
            "📊 SCORES",
            f"  Tree Edit Distance : {ted}",
            f"  Similarity Score   : {sim:.1%}",
            f"  T1 nodes ({c1}) : {result['tree1_size']}",
            f"  T2 nodes ({c2}) : {result['tree2_size']}\n",
        ]

        if sim >= 0.85:
            emoji, label = "🟢", "Very Similar"
        elif sim >= 0.65:
            emoji, label = "🟡", "Similar"
        elif sim >= 0.40:
            emoji, label = "🟠", "Somewhat Different"
        else:
            emoji, label = "🔴", "Very Different"

        lines.extend([
            f"{emoji}  Interpretation: {label}\n",
            "✏️  EDIT SCRIPT SUMMARY",
            f"  Total operations : {es['total_operations']}",
            f"  Matches (no cost): {es['matches']}",
            f"  Updates          : {es['updates']}",
            f"  Inserts          : {es['inserts']}",
            f"  Deletes          : {es['deletes']}\n",
        ])

        non_matches = [o for o in es['operations'] if o['op'] != 'match']
        if non_matches:
            lines.append("⚠️  TOP DIFFERENCES (by cost)")
            top = sorted(non_matches, key=lambda x: -x['cost'])[:6]
            for op in top:
                if op['op'] == 'update':
                    token1 = op.get('token1', {})
                    token2 = op.get('token2', {})
                    
                    if token1 and token2 and token1.get('base') == token2.get('base'):
                        lines.append(f"  UPDATE (parameter difference) [{token1['base']}]")
                        lines.append(f"    {c1}: params={token1['params']}, type={token1['type']}")
                        lines.append(f"    {c2}: params={token2['params']}, type={token2['type']}")
                    else:
                        if op['label1'] != op['label2']:
                            lines.append(f"  UPDATE (structural)")
                            lines.append(f"    {c1} field: {op['label1']}")
                            lines.append(f"    {c2} field: {op['label2']}")
                        else:
                            lines.append(f"  UPDATE [{op['label1']}]")
                            lines.append(f"    {c1}: {str(op['value1'] or '')[:60]}")
                            lines.append(f"    {c2}: {str(op['value2'] or '')[:60]}")
                elif op['op'] == 'insert':
                    lines.append(f"  INSERT [{op['label2']}] = {str(op['value2'] or '')[:50]} (only in {c2})")
                elif op['op'] == 'delete':
                    lines.append(f"  DELETE [{op['label1']}] = {str(op['value1'] or '')[:50]} (only in {c1})")
                lines.append(f"    cost = {op['cost']}\n")

        lines.extend([
            f"{'='*55}",
            "Algorithm: Chawathe TED (VLDB 1999)",
            "Features:",
            "  - Field Tokenization: Parentheses(), Brackets[], Underscore_",
            "  - Optimal Item Reordering: Cross-tree fuzzy matching",
            "  - Similarity-based cost (0.0-0.5) for all differences",
        ])

        return '\n'.join(lines)


# ─────────────────────────────────────────────
#  Quick demo
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    c1 = sys.argv[1] if len(sys.argv) > 1 else 'Lebanon'
    c2 = sys.argv[2] if len(sys.argv) > 2 else 'Switzerland'

    print(f"\nLoading '{c1}' and '{c2}'...")

    db = WikipediaDatabase()
    comp = TEDComparator()

    data1 = db.get_country(c1)
    data2 = db.get_country(c2)

    if not data1 or not data2:
        print("Countries not found.")
        sys.exit(1)

    data1.pop('_id', None)
    data2.pop('_id', None)

    result = comp.compare_countries(data1, data2)
    report = comp.generate_report(result)

    print(report)