"""Layer 4: Exact-match validation - for control prompt determinism checks."""

from typing import Tuple


def exact_match_check(candidate_output: str, expected_output: str) -> Tuple[bool, str]:
    """
    Layer 4 exact-match validation.

    Used only for control_prompt scenario to detect determinism drift.
    Strips whitespace but requires content to be identical.

    Args:
        candidate_output: Generated output
        expected_output: Expected exact output

    Returns:
        Tuple of (passed, message)
        - True means check passed (match found)
        - False means check failed (no match)
        - Caller will interpret False as WARN level, not hard FAIL,
          since hardware variation can affect determinism even at T=0
    """

    candidate_cleaned = candidate_output.strip()
    expected_cleaned = expected_output.strip()

    if candidate_cleaned == expected_cleaned:
        return True, f"Exact match: '{expected_cleaned}'"
    else:
        # Return False for mismatch (will be WARN level by caller)
        return False, (
            f"Exact match failed. Expected: '{expected_cleaned}' "
            f"Got: '{candidate_cleaned}' (hardware may affect T=0 determinism)"
        )