"""
list_item_matcher.py — List-item matching with a cost matrix.

Provides ListItemMatcher class for optimal matching of list items
using cost matrix and bipartite assignment.
Also includes helper functions for extracting and matching list items.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np
from difflib import SequenceMatcher
from field_tokenizer import FieldTokenizer
from tree_builder import TreeNode


class ListItemMatcher:
    """Match list items using cost matrix and optimal assignment."""
    
    def __init__(self):
        self.tokenizer = FieldTokenizer()
    
    def cost_update(self, val1: str, val2: str) -> float:
        """Cost to update val1 to val2."""
        if val1 == val2:
            return 0.0
        sim = SequenceMatcher(None, val1 or '', val2 or '').ratio()
        return 0.5 * (1.0 - sim)
    
    def build_cost_matrix(self, items_a: List[Tuple[str, str]], 
                         items_b: List[Tuple[str, str]]) -> np.ndarray:
        """
        Build cost matrix for all item pairs.
        
        Args:
            items_a: List of (label, value) tuples from tree A
            items_b: List of (label, value) tuples from tree B
        
        Returns:
            Cost matrix of shape (len(items_a), len(items_b))
        """
        n = len(items_a)
        m = len(items_b)
        matrix = np.zeros((n, m))
        
        for i, (label_a, val_a) in enumerate(items_a):
            for j, (label_b, val_b) in enumerate(items_b):
                # Compare values
                sim = SequenceMatcher(None, val_a or '', val_b or '').ratio()
                matrix[i][j] = 0.5 * (1.0 - sim)
        
        return matrix
    
    def optimal_assignment(self, cost_matrix: np.ndarray) -> List[Tuple[int, int, float]]:
        """
        Find optimal bipartite matching using linear sum assignment.
        Falls back to greedy if scipy not available.
        
        Args:
            cost_matrix: 2D numpy array of costs
        
        Returns:
            List of (i, j, cost) tuples representing the matching
        """
        try:
            from scipy.optimize import linear_sum_assignment
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            return [(i, j, cost_matrix[i][j]) for i, j in zip(row_ind, col_ind)]
        except ImportError:
            # Greedy fallback if scipy not available
            used = set()
            matches = []
            for i in range(len(cost_matrix)):
                best_j = None
                best_cost = float('inf')
                for j in range(len(cost_matrix[0])):
                    if j not in used and cost_matrix[i][j] < best_cost:
                        best_cost = cost_matrix[i][j]
                        best_j = j
                if best_j is not None:
                    matches.append((i, best_j, best_cost))
                    used.add(best_j)
            return matches
    
    def print_cost_matrix(self, cost_matrix: np.ndarray,
                         items_a: List[Tuple[str, str]],
                         items_b: List[Tuple[str, str]]) -> None:
        """
        Pretty-print the cost matrix for debugging.
        
        Args:
            cost_matrix: 2D numpy array of costs
            items_a: List of (label, value) tuples from tree A
            items_b: List of (label, value) tuples from tree B
        """
        print(f"\n💰 COST MATRIX:")
        print(f"   {'A items':<40} | B cost matrix")
        print(f"   {'-'*40} | {'-'*60}")
        
        for i, (label_a, val_a) in enumerate(items_a):
            display_val = f"{val_a[:35]}" if val_a else "None"
            print(f"   A[{i}] {display_val:<36} | ", end='')
            for j in range(len(items_b)):
                print(f"B[{j}]={cost_matrix[i][j]:.4f} ", end='')
            print()
        
        print()
    
    def print_matches(self, matches: List[Tuple[int, int, float]],
                     items_a: List[Tuple[str, str]],
                     items_b: List[Tuple[str, str]]) -> None:
        """
        Pretty-print the optimal matching result.
        
        Args:
            matches: List of (i, j, cost) tuples from optimal_assignment
            items_a: List of (label, value) tuples from tree A
            items_b: List of (label, value) tuples from tree B
        """
        print(f"\n✅ OPTIMAL MATCHING:")
        total_cost = 0.0
        
        for i, j, cost in matches:
            val_a = items_a[i][1] if i < len(items_a) else "N/A"
            val_b = items_b[j][1] if j < len(items_b) else "N/A"
            
            print(f"   A[{i}] → B[{j}] (cost={cost:.4f})")
            print(f"     '{str(val_a)[:50]}' ↔ '{str(val_b)[:50]}'")
            total_cost += cost
        
        print(f"   Total matching cost: {total_cost:.4f}\n")


# ─────────────────────────────────────────────
#  Helper Functions for List Extraction
# ─────────────────────────────────────────────

def extract_list_items(root: TreeNode) -> Dict[str, List[str]]:
    """
    Extract all list items by field.
    
    Args:
        root: Root TreeNode of the document tree
    
    Returns: 
        Dictionary mapping {field_name: [item_values]}
    """
    lists = {}
    
    def traverse(node: TreeNode):
        if node.label in ['item', 'sub_item'] and node.parent:
            field_name = node.parent.label
            if field_name not in lists:
                lists[field_name] = []
            
            # Get text value
            if node.children and node.children[0].node_type == 'text':
                lists[field_name].append(node.children[0].value)
        
        for child in node.children:
            traverse(child)
    
    traverse(root)
    return lists


def match_list_items(lists_a: Dict[str, List[str]], 
                     lists_b: Dict[str, List[str]],
                     debug: bool = True) -> Dict[str, List[Tuple[int, int, float]]]:
    """
    Match list items for all common fields.
    
    Args:
        lists_a: Dictionary of list items from tree A
        lists_b: Dictionary of list items from tree B
        debug: Whether to print debug output
    
    Returns: 
        Dictionary mapping {field_name: [(idx_a, idx_b, cost), ...]}
    """
    matcher = ListItemMatcher()
    matchings = {}
    
    for field in lists_a:
        if field in lists_b:
            items_a = lists_a[field]
            items_b = lists_b[field]
            
            if len(items_a) > 0 and len(items_b) > 0:
                cost_matrix = matcher.build_cost_matrix(items_a, items_b)
                matches = matcher.optimal_assignment(cost_matrix)
                matchings[field] = matches
                
                if debug:
                    print(f"\n📋 FIELD: {field}")
                    print(f"   Items A: {items_a}")
                    print(f"   Items B: {items_b}")
                    print(f"   Matchings:")
                    for i, j, cost in matches:
                        print(f"     A[{i}] → B[{j}]  (cost={cost:.4f})  '{items_a[i]}' ↔ '{items_b[j]}'")
    
    return matchings


def remove_list_items(node: TreeNode) -> Optional[TreeNode]:
    """
    Create a copy of the tree with list items removed.
    
    Args:
        node: TreeNode to clone and prune
    
    Returns:
        New TreeNode with list items removed, or None if node is a list item
    """
    if node.label in ['item', 'sub_item']:
        return None  # Skip this node
    
    # Create copy
    new_node = TreeNode(label=node.label, node_type=node.node_type, value=node.value)
    new_node.node_id = node.node_id
    
    # Recursively copy children (excluding list items)
    for child in node.children:
        new_child = remove_list_items(child)
        if new_child:
            new_node.add_child(new_child)
    
    return new_node