"""
field_tokenizer.py — Field-name tokenization for parameter extraction.

Implements three types of field name tokenization:
1. PARENTHESES: Field(param) -> base="field", params=["param"]
2. BRACKETS: Field[param] -> base="field", params=["param"]
3. UNDERSCORE: Field_param -> base="field", params=["param"]

Also handles mixed delimiters and extracts multiple parameters.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TokenizedField:
    """Result of tokenizing a field name."""
    original: str              # Original field name (e.g., "Population(2021)")
    base_name: str             # Base name normalized (e.g., "population")
    parameters: List[str]      # Extracted parameters (e.g., ["2021"])
    tokenization_type: str     # Type used: "parentheses", "brackets", "underscore", or "none"

    def __repr__(self):
        param_str = f", params={self.parameters}" if self.parameters else ""
        return f"TokenizedField(original={self.original!r}, base={self.base_name!r}{param_str}, type={self.tokenization_type!r})"


class FieldTokenizer:
    """
    Tokenizes field names to extract base names and parameters.
    
    Three tokenization types (in order of priority):
    1. PARENTHESES: "Population(2021)" or "Area(km2)"
    2. BRACKETS: "Population[2021]" or "Area[km2]"
    3. UNDERSCORE: "Population_2021" or "Area_km2"
    """

    # ─────────────────────────────────────────────────────────────────
    #  Tokenization Patterns
    # ─────────────────────────────────────────────────────────────────

    # Pattern 1: Parentheses - Field(param1, param2, ...)
    PARENTHESES_PATTERN = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*([^)]+)\s*\)$"
    )

    # Pattern 2: Brackets - Field[param1, param2, ...]
    BRACKETS_PATTERN = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\s*([^\]]+)\s*\]$"
    )

    # Pattern 3: Underscore - Field_param or Field_param1_param2
    # (matches one or more underscore-separated components after base)
    UNDERSCORE_PATTERN = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9]*?)(?:_([a-zA-Z0-9_]+))$"
    )

    @staticmethod
    def normalize_base_name(name: str) -> str:
        """
        Normalize base name for comparison:
        - Convert to lowercase
        - Replace non-alphanumeric (except underscore) with underscore
        - Remove leading/trailing underscores
        - Remove multiple consecutive underscores
        """
        normalized = name.lower().strip()
        normalized = re.sub(r'[^a-z0-9_]', '_', normalized)
        normalized = re.sub(r'_+', '_', normalized)
        normalized = normalized.strip('_')
        
        # Handle leading digits (XML restriction)
        if normalized and normalized[0].isdigit():
            normalized = 'y' + normalized
        
        return normalized if normalized else 'field'

    @staticmethod
    def extract_parameters(param_string: str) -> List[str]:
        """
        Extract individual parameters from a comma-separated parameter string.
        Strips whitespace from each parameter.
        """
        if not param_string:
            return []
        
        params = [p.strip() for p in param_string.split(',')]
        return [p for p in params if p]  # Remove empty strings

    def tokenize(self, field_name: str) -> TokenizedField:
        """
        Tokenize a field name using all three types in priority order.
        
        Returns:
            TokenizedField with original name, base name, parameters, and type used.
        """
        if not field_name or not isinstance(field_name, str):
            return TokenizedField(
                original=str(field_name) if field_name else "",
                base_name="field",
                parameters=[],
                tokenization_type="none"
            )

        field_name = field_name.strip()

        # ── Type 1: Parentheses ───────────────────────────────��────────
        match = self.PARENTHESES_PATTERN.match(field_name)
        if match:
            base = match.group(1)
            param_str = match.group(2)
            return TokenizedField(
                original=field_name,
                base_name=self.normalize_base_name(base),
                parameters=self.extract_parameters(param_str),
                tokenization_type="parentheses"
            )

        # ── Type 2: Brackets ───────────────────────────────────────────
        match = self.BRACKETS_PATTERN.match(field_name)
        if match:
            base = match.group(1)
            param_str = match.group(2)
            return TokenizedField(
                original=field_name,
                base_name=self.normalize_base_name(base),
                parameters=self.extract_parameters(param_str),
                tokenization_type="brackets"
            )

        # ── Type 3: Underscore ─────────────────────────────────────────
        match = self.UNDERSCORE_PATTERN.match(field_name)
        if match:
            base = match.group(1)
            param_part = match.group(2)
            params = [p.strip() for p in param_part.split('_') if p.strip()]
            return TokenizedField(
                original=field_name,
                base_name=self.normalize_base_name(base),
                parameters=params,
                tokenization_type="underscore"
            )

        # ── No recognized pattern ──────────────────────────────────────
        # Just normalize the entire field as base name
        return TokenizedField(
            original=field_name,
            base_name=self.normalize_base_name(field_name),
            parameters=[],
            tokenization_type="none"
        )

    def tokenize_batch(self, field_names: List[str]) -> Dict[str, TokenizedField]:
        """
        Tokenize multiple field names and return as a dictionary.
        
        Args:
            field_names: List of field names
            
        Returns:
            Dictionary mapping original name -> TokenizedField
        """
        return {name: self.tokenize(name) for name in field_names}

    def get_comparable_key(self, field_name: str) -> Tuple[str, tuple]:
        """
        Get a comparison key for sorting/grouping by base name and parameters.
        
        Returns:
            (base_name, tuple_of_params) for use in comparisons
        """
        tokenized = self.tokenize(field_name)
        return (tokenized.base_name, tuple(tokenized.parameters))


# ─────────────────────────────────────────────────────────────────
#  Convenience function
# ─────────────────────────────────────────────────────────────────

def tokenize_field(field_name: str) -> TokenizedField:
    """Quick tokenization using default tokenizer."""
    tokenizer = FieldTokenizer()
    return tokenizer.tokenize(field_name)


# ─────────────────────────────────────────────────────────────────
#  Demo and Tests
# ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tokenizer = FieldTokenizer()

    # Test cases demonstrating all three tokenization types
    test_fields = [
        # Parentheses type
        "Population(2021)",
        "Area(km2)",
        "GDP(USD 2020)",
        "Population(2021, estimated)",

        # Brackets type
        "Population[2021]",
        "Area[km2]",
        "GDP[USD]",

        # Underscore type
        "Population_2021",
        "Area_km2",
        "GDP_USD_2020",

        # No recognized pattern
        "Population",
        "Area",
        "country_name",

        # Edge cases
        "Pop()",
        "Area[]",
        "Field_",
        "_Field",
    ]

    print("=" * 80)
    print("  Field Tokenizer Test Suite")
    print("=" * 80)
    print()

    for field in test_fields:
        result = tokenizer.tokenize(field)
        print(f"Input:  {field!r:30} -> {result}")

    print()
    print("=" * 80)
    print("  Comparison Keys (for grouping)")
    print("=" * 80)
    print()

    for field in test_fields[:5]:
        key = tokenizer.get_comparable_key(field)
        print(f"{field!r:30} -> key={key}")