"""Pre-flight conformance check for LLM service endpoints."""

import asyncio
import httpx
from typing import Tuple, List

class ConformanceError(Exception):
    """Raised when endpoint does not meet conformance requirements."""
    pass


async def check_conformance(endpoint_url: str, timeout: float = 10.0) -> Tuple[bool, str]:
    """
    Check if an endpoint conforms to the Turing benchmark requirements.

    Args:
        endpoint_url: Base URL of the service (e.g., http://localhost:8000)
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_conformant, message)

    Checks:
    - Endpoint responds to POST /v1/chat/completions
    - Returns SSE stream with stream: true
    - SSE format matches OpenAI contract
    - data: [DONE] termination is present
    - First token chunk is detectable
    """

    checks: List[Tuple[str, bool, str]] = []

    try:
        # Test 1: Endpoint exists and responds
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # Send a minimal conformance test request
                response = await client.post(
                    f"{endpoint_url}/v1/chat/completions",
                    json={
                        "model": "test",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "stream": True,
                        "max_tokens": 10,
                    },
                )

                checks.append(("Endpoint responds", response.status_code == 200, ""))

                if response.status_code != 200:
                    return False, f"Endpoint returned status {response.status_code}"

                # Test 2: Response has proper SSE format
                is_sse = False
                has_done_signal = False
                has_content_chunk = False

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    if line.startswith("data: "):
                        data = line[6:].strip()
                        is_sse = True

                        if data == "[DONE]":
                            has_done_signal = True
                        elif data.startswith("{"):
                            # Try to parse as JSON to verify format
                            try:
                                import json
                                chunk = json.loads(data)
                                # Check for content in choices
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})
                                    if delta.get("content"):
                                        has_content_chunk = True
                            except json.JSONDecodeError:
                                pass

                checks.append(("SSE format detected", is_sse, ""))
                checks.append(("Has [DONE] signal", has_done_signal, ""))
                checks.append(("Has content chunks", has_content_chunk, ""))

                # Test 3: Verify timeout handling
                checks.append(("Responds within timeout", True, ""))

            except httpx.TimeoutException:
                return False, "Endpoint timed out during conformance check"
            except httpx.ConnectError as e:
                return False, f"Cannot connect to endpoint: {e}"

    except Exception as e:
        return False, f"Conformance check failed: {str(e)}"

    # Summary
    all_passed = all(passed for _, passed, _ in checks)

    if all_passed:
        summary = "✓ Conformant with Turing benchmark requirements"
    else:
        failed = [name for name, passed, _ in checks if not passed]
        summary = f"✗ Not conformant. Failed checks: {', '.join(failed)}"

    return all_passed, summary


def sync_check_conformance(endpoint_url: str, timeout: float = 10.0) -> Tuple[bool, str]:
    """Synchronous wrapper for check_conformance."""
    return asyncio.run(check_conformance(endpoint_url, timeout))
