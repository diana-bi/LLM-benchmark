"""Layer 1: Sanity checks - pure string validation."""

from typing import Tuple


def sanity_check(output: str, min_length: int, max_length: int) -> Tuple[bool, str]:
    """
    Layer 1 sanity validation.

    Checks:
    - Output is not None or empty
    - Output doesn't end abruptly mid-sentence
    - Token count is within bounds

    Args:
        output: Generated output string
        min_length: Minimum token count (rough estimate: 1 token ≈ 1.3 words)
        max_length: Maximum token count

    Returns:
        Tuple of (passed, message)
    """

    if not output or output.strip() == "":
        return False, "Output is empty"

    # Check for abrupt ending (ends with incomplete thought markers)
    abrupt_endings = ["...", "(...", "[..."]
    if any(output.rstrip().endswith(marker) for marker in abrupt_endings):
        return False, "Output appears to end abruptly"

    # Estimate token count (rough: split by whitespace, 1 token ≈ 1.3 words)
    word_count = len(output.split())
    estimated_tokens = word_count

    if estimated_tokens < min_length:
        return False, f"Output too short: {estimated_tokens} tokens < {min_length} minimum"

    if estimated_tokens > max_length:
        return False, f"Output too long: {estimated_tokens} tokens > {max_length} maximum"

    return True, "Sanity check passed"
