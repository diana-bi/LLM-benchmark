"""Layer 2: Structural validation - JSON, code syntax, etc."""

import json
import ast
from typing import Tuple


def structural_check(output: str, check_json: bool = False, check_python: bool = False) -> Tuple[bool, str]:
    """
    Layer 2 structural validation.

    Checks format-specific constraints:
    - JSON validity if check_json=True
    - Python syntax if check_python=True

    Args:
        output: Generated output string
        check_json: Whether to validate as JSON
        check_python: Whether to validate as Python code

    Returns:
        Tuple of (passed, message)
    """

    if check_json:
        try:
            json.loads(output)
            return True, "JSON validation passed"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {str(e)}"

    if check_python:
        try:
            ast.parse(output)
            return True, "Python syntax validation passed"
        except SyntaxError as e:
            return False, f"Invalid Python syntax: {str(e)}"

    # No structural checks requested
    return True, "No structural checks configured"
