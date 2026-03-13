"""Live terminal dashboard for real-time benchmark observability.

Uses Rich to render a live-updating panel during the concurrent phase,
showing latency distribution, running percentiles, drift signal, and spike count
as requests complete — rather than only reporting at the end.

Usage (from benchmark.py):
    dashboard = LiveDashboard(scenario_name, total_requests, rps)
    with dashboard.live_context():
        results = await conc_runner.run_scenario(
            scenario_cfg, rps, num_requests, stats_collector=dashboard
        )
        dashboard.finalize()
"""

import asyncio
from typing import List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn


class LiveDashboard:
    """
    Accumulates per-request results and renders a live Rich panel.

    Thread-safe: on_result() is called from asyncio tasks but Rich's Live
    is safe to update from any coroutine in the same event loop.
    """

    def __init__(self, scenario_name: str, total_requests: int, rps: int):
        self.scenario_name = scenario_name
        self.total_requests = total_requests
        self.rps = rps

        # Accumulated data
        self.latencies: List[float] = []
        self.ttft_values: List[float] = []
        self.errors: int = 0
        self.completed: int = 0

        self._live: Optional[Live] = None

    # ------------------------------------------------------------------ #
    # Callback — called by ConcurrentRunner for each completed request    #
    # ------------------------------------------------------------------ #

    def on_result(self, result) -> None:
        """Called by ConcurrentRunner after each request completes."""
        self.completed += 1
        if result.error:
            self.errors += 1
        else:
            self.latencies.append(result.total_time_ms)
            if result.ttft_ms > 0:
                self.ttft_values.append(result.ttft_ms)

    # ------------------------------------------------------------------ #
    # Rendering                                                            #
    # ------------------------------------------------------------------ #

    def _stats_table(self) -> Table:
        """Build a Rich table with running percentile stats."""
        table = Table(box=None, padding=(0, 2), expand=True)
        table.add_column("Metric", style="dim", width=10)
        table.add_column("Value", justify="right")
        table.add_column("Metric", style="dim", width=10)
        table.add_column("Value", justify="right")

        if not self.latencies:
            table.add_row("Waiting…", "", "", "")
            return table

        n = len(self.latencies)
        sorted_lats = sorted(self.latencies)

        p50 = sorted_lats[n // 2]
        p95 = sorted_lats[min(int(n * 0.95), n - 1)]
        p99 = sorted_lats[min(int(n * 0.99), n - 1)]
        mean = sum(self.latencies) / n
        median = p50
        spike_threshold = median * 2.5
        spike_count = sum(1 for lat in self.latencies if lat > spike_threshold)

        # CV
        variance = sum((x - mean) ** 2 for x in self.latencies) / n
        cv = (variance ** 0.5 / mean * 100) if mean > 0 else 0.0

        # TTFT
        ttft_p50 = ""
        if self.ttft_values:
            sorted_ttft = sorted(self.ttft_values)
            ttft_p50 = f"{sorted_ttft[len(sorted_ttft) // 2]:.0f}ms"

        cv_color = "green" if cv < 10 else "yellow" if cv < 20 else "red"
        spike_color = "green" if spike_count == 0 else "yellow"
        err_color = "green" if self.errors == 0 else "red"

        table.add_row(
            "P50", f"{p50:.0f}ms",
            "P99", f"{p99:.0f}ms",
        )
        table.add_row(
            "P95", f"{p95:.0f}ms",
            "TTFT P50", ttft_p50 or "n/a",
        )
        table.add_row(
            "Mean", f"{mean:.0f}ms",
            "CV", Text(f"{cv:.1f}%", style=cv_color),
        )
        table.add_row(
            "Spikes", Text(f"{spike_count}", style=spike_color),
            "Errors", Text(f"{self.errors}", style=err_color),
        )

        return table

    def _histogram(self, bins: int = 10, bar_width: int = 24) -> Text:
        """Build a Text block with an ASCII histogram of current latencies."""
        if len(self.latencies) < 2:
            return Text("  collecting data…", style="dim")

        lats = self.latencies
        min_lat = min(lats)
        max_lat = max(lats)

        if max_lat == min_lat:
            return Text(f"  all values = {min_lat:.0f}ms", style="dim")

        n = len(lats)
        sorted_lats = sorted(lats)
        p50 = sorted_lats[n // 2]
        p95 = sorted_lats[min(int(n * 0.95), n - 1)]

        bin_size = (max_lat - min_lat) / bins
        counts = [0] * bins
        for lat in lats:
            idx = min(int((lat - min_lat) / bin_size), bins - 1)
            counts[idx] += 1

        max_count = max(counts) or 1
        text = Text()

        for i, count in enumerate(counts):
            bin_start = min_lat + i * bin_size
            bin_end = bin_start + bin_size
            bar_len = int((count / max_count) * bar_width)
            bar = "█" * bar_len

            markers = []
            if bin_start <= p50 < bin_end:
                markers.append("P50")
            if bin_start <= p95 < bin_end:
                markers.append("P95")
            marker = " ← " + "/".join(markers) if markers else ""

            bar_color = "green" if i < bins // 3 else "yellow" if i < bins * 2 // 3 else "red"
            text.append(f"  {bin_start:6.0f}─{bin_end:<6.0f}ms │")
            text.append(f"{bar:<{bar_width}}", style=bar_color)
            text.append(f" {count:>4}{marker}\n")

        return text

    def _drift_signal(self) -> str:
        """Quick drift signal: compare first-half mean to second-half mean."""
        n = len(self.latencies)
        if n < 20:
            return ""
        mid = n // 2
        first_mean = sum(self.latencies[:mid]) / mid
        second_mean = sum(self.latencies[mid:]) / (n - mid)
        drift_pct = (second_mean - first_mean) / first_mean * 100 if first_mean > 0 else 0
        if abs(drift_pct) < 3:
            return ""
        icon = "⚠ " if abs(drift_pct) > 5 else ""
        direction = "↑ slowing" if drift_pct > 0 else "↓ improving"
        return f"  {icon}Drift: {drift_pct:+.1f}% ({direction})\n"

    def make_panel(self) -> Panel:
        """Render the full live panel."""
        progress_pct = self.completed / self.total_requests * 100 if self.total_requests > 0 else 0
        bar_filled = int(progress_pct / 2)  # 50-char progress bar
        bar = "█" * bar_filled + "░" * (50 - bar_filled)

        header = Text()
        header.append(f"\n  {bar} ", style="cyan")
        header.append(f"{self.completed}/{self.total_requests}", style="bold")
        header.append(f"  ({progress_pct:.0f}%  {self.rps} RPS)\n\n")

        stats = self._stats_table()
        hist = self._histogram()
        drift = self._drift_signal()

        layout = Text()
        if drift:
            layout.append(drift, style="yellow")

        from rich.console import Console, Group
        from rich.rule import Rule

        return Panel(
            Group(
                header,
                stats,
                Rule(style="dim"),
                Text("\n  Latency distribution (live)\n", style="dim"),
                hist,
            ),
            title=f"[bold cyan]{self.scenario_name}[/bold cyan]  [dim]concurrent phase[/dim]",
            border_style="cyan",
            expand=True,
        )

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def live_context(self) -> "LiveDashboard":
        """Return self for use as context manager."""
        return self

    def __enter__(self):
        self._live = Live(
            self.make_panel(),
            refresh_per_second=4,
            transient=False,
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.update(self.make_panel())
            self._live.__exit__(*args)

    def update(self) -> None:
        """Push a display refresh (call this periodically while requests run)."""
        if self._live:
            self._live.update(self.make_panel())

    def finalize(self) -> None:
        """Force a final render with 100% completion."""
        if self._live:
            self._live.update(self.make_panel())
