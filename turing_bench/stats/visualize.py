"""ASCII terminal visualizations for latency observability.

Produces charts that work in any terminal without external dependencies.
Designed for two use cases:
  - Time-series: latency vs run index (shows drift, spikes)
  - Histogram:   frequency vs latency bucket (shows shape, fat tails, bimodal)
"""

from typing import List


def ascii_time_series(
    latencies: List[float],
    title: str = "",
    width: int = 60,
    height: int = 6,
) -> str:
    """
    ASCII time-series chart of latency vs run index.

    Reveals:
    - Drift: upward slope across runs
    - Spikes: isolated vertical outliers (marked with ●)
    - Stability: flat line = healthy

    Args:
        latencies: Ordered list of latency values in ms
        title:     Optional label printed above the chart
        width:     Character width of the plot area
        height:    Number of rows in the plot area

    Returns:
        Multi-line string ready for print()
    """
    if not latencies or len(latencies) < 2:
        return ""

    n = len(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)

    if max_lat == min_lat:
        return f"  {title + ': ' if title else ''}all values = {min_lat:.0f}ms"

    sorted_lats = sorted(latencies)
    median_lat = sorted_lats[n // 2]
    spike_threshold = median_lat * 2.5

    # Build empty grid
    grid = [[" "] * width for _ in range(height)]

    # Plot each latency as a point
    for i, lat in enumerate(latencies):
        x = min(int((i / (n - 1)) * (width - 1)), width - 1)
        y_norm = (lat - min_lat) / (max_lat - min_lat)
        y_flipped = height - 1 - min(int(y_norm * (height - 1)), height - 1)
        grid[y_flipped][x] = "●" if lat > spike_threshold else "·"

    # Median reference line
    median_y_norm = (median_lat - min_lat) / (max_lat - min_lat)
    median_row = height - 1 - min(int(median_y_norm * (height - 1)), height - 1)
    for x in range(width):
        if grid[median_row][x] == " ":
            grid[median_row][x] = "─"

    lines = []
    if title:
        lines.append(f"  {title}")

    for i, row in enumerate(grid):
        if i == 0:
            y_label = f"{max_lat:7.0f}ms"
        elif i == median_row:
            y_label = f"{median_lat:7.0f}ms"
        elif i == height - 1:
            y_label = f"{min_lat:7.0f}ms"
        else:
            y_label = " " * 9
        lines.append(f"  {y_label} │{''.join(row)}")

    lines.append(f"            └{'─' * width}")
    mid_label = str(n // 2)
    end_label = str(n)
    lines.append(
        f"             1{mid_label:^{width // 2 - 1}}{end_label:>{width // 2 - 1}}"
    )

    has_spikes = any(lat > spike_threshold for lat in latencies)
    if has_spikes:
        lines.append(f"            · normal  ● spike (>{spike_threshold:.0f}ms)")
    else:
        lines.append(f"            ─── P50={median_lat:.0f}ms  · requests")

    return "\n".join(lines)


def ascii_histogram(
    latencies: List[float],
    title: str = "",
    bins: int = 10,
    bar_width: int = 28,
) -> str:
    """
    ASCII histogram of latency distribution.

    Reveals:
    - Fat tails:  long bar on the right with few requests
    - Bimodal:    two separate clusters of bars
    - Skewness:   asymmetry around the median

    Args:
        latencies: List of latency values in ms (order doesn't matter)
        title:     Optional label printed above the chart
        bins:      Number of buckets
        bar_width: Maximum bar length in characters

    Returns:
        Multi-line string ready for print()
    """
    if not latencies or len(latencies) < 2:
        return ""

    min_lat = min(latencies)
    max_lat = max(latencies)

    if max_lat == min_lat:
        return f"  {title + ': ' if title else ''}all values = {min_lat:.0f}ms"

    n = len(latencies)
    sorted_lats = sorted(latencies)
    median_lat = sorted_lats[n // 2]
    p95_lat = sorted_lats[min(int(n * 0.95), n - 1)]
    p99_lat = sorted_lats[min(int(n * 0.99), n - 1)]

    bin_size = (max_lat - min_lat) / bins
    counts = [0] * bins
    for lat in latencies:
        idx = min(int((lat - min_lat) / bin_size), bins - 1)
        counts[idx] += 1

    max_count = max(counts) or 1

    lines = []
    if title:
        lines.append(f"  {title}")

    for i, count in enumerate(counts):
        bin_start = min_lat + i * bin_size
        bin_end = bin_start + bin_size
        bar_len = int((count / max_count) * bar_width)
        bar = "█" * bar_len

        # Mark percentile positions within this bin
        markers = []
        if bin_start <= median_lat < bin_end:
            markers.append("P50")
        if bin_start <= p95_lat < bin_end:
            markers.append("P95")
        if bin_start <= p99_lat < bin_end:
            markers.append("P99")
        marker = " ← " + "/".join(markers) if markers else ""

        lines.append(
            f"  {bin_start:6.0f}─{bin_end:<6.0f}ms │{bar:<{bar_width}} {count:>4}{marker}"
        )

    return "\n".join(lines)
