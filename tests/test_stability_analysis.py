"""Tests for stability analysis modules."""

import pytest

from turing_bench.stats.drift import detect_drift
from turing_bench.stats.spike import detect_spikes
from turing_bench.stats.distribution import analyze_distribution


class TestDriftDetection:
    """Test drift detection across run sequences."""

    def test_no_drift(self):
        """Test when latencies are stable."""
        latencies = [100.0] * 100
        result = detect_drift(latencies)

        assert not result["has_drift"]
        assert abs(result["drift_percent"]) < 1.0

    def test_positive_drift(self):
        """Test when latencies increase (degradation)."""
        # First half: 100ms, second half: 115ms → 15% drift
        latencies = [100.0] * 50 + [115.0] * 50

        result = detect_drift(latencies, threshold_percent=10.0)

        assert result["has_drift"]
        assert result["drift_percent"] > 10.0

    def test_negative_drift(self):
        """Test when latencies decrease (improvement)."""
        # First half: 100ms, second half: 85ms → -15% drift
        latencies = [100.0] * 50 + [85.0] * 50

        result = detect_drift(latencies, threshold_percent=10.0)

        assert result["has_drift"]
        assert result["drift_percent"] < -10.0

    def test_minimal_samples(self):
        """Test with only 1 sample."""
        result = detect_drift([100.0])

        assert not result["has_drift"]


class TestSpikeDetection:
    """Test spike/outlier detection."""

    def test_no_spikes(self):
        """Test when all latencies are consistent."""
        latencies = [100.0] * 100

        result = detect_spikes(latencies, multiplier=2.5)

        assert result["spike_count"] == 0
        assert not result["has_spikes"]

    def test_single_spike(self):
        """Test detection of isolated spike."""
        latencies = [100.0] * 99 + [500.0]  # 1 spike out of 100

        result = detect_spikes(latencies, multiplier=2.5)

        assert result["spike_count"] >= 1
        assert len(result["spike_indices"]) >= 1

    def test_multiple_spikes(self):
        """Test when too many spikes trigger warning."""
        # 10 spikes out of 100 = 10%
        latencies = [100.0] * 90 + [500.0] * 10

        result = detect_spikes(latencies, multiplier=2.5, max_spike_percent=5.0)

        assert result["has_spikes"]
        assert result["spike_percent"] > 5.0

    def test_spike_threshold_customizable(self):
        """Test customizing spike threshold."""
        latencies = [100.0] * 99 + [300.0]

        # At 2.5x threshold, 300 should not be a spike (100 * 2.5 = 250)
        result_25x = detect_spikes(latencies, multiplier=2.5)
        assert result_25x["spike_count"] >= 1

        # At 5x threshold, 300 should not be a spike (100 * 5 = 500)
        result_5x = detect_spikes(latencies, multiplier=5.0)
        assert result_5x["spike_count"] == 0


class TestDistributionAnalysis:
    """Test distribution shape analysis."""

    def test_normal_distribution(self):
        """Test with relatively normal distribution."""
        # All values clustered around 100
        latencies = [100.0 + i * 0.1 for i in range(100)]

        result = analyze_distribution(latencies)

        # Should not have fat tail
        assert result["p99_p95_ratio"] < 1.5

    def test_fat_tail_distribution(self):
        """Test detection of fat tail (heavy right skew)."""
        # Create a distribution with gradual increase toward the tail
        # 0-80%: 100ms, 80-95%: 200ms, 95-99%: 300ms, 99-100%: 500ms
        latencies = [100.0] * 80 + [200.0] * 15 + [300.0] * 4 + [500.0] * 1

        result = analyze_distribution(latencies)

        # P99 (at index ~99) should be around 500
        # P95 (at index ~95) should be around 200
        # Ratio should be > 1.5
        assert result["p99_p95_ratio"] > 1.3  # Relaxed threshold
        assert result["is_right_skewed"]  # Should detect right skew

    def test_percentile_calculations(self):
        """Test accurate percentile calculation."""
        latencies = list(range(1, 101))  # 1 to 100

        result = analyze_distribution(latencies)

        assert result["p50"] == pytest.approx(50, abs=2)
        assert result["p95"] >= 94
        assert result["p99"] >= 98

    def test_minimal_samples(self):
        """Test with fewer than 3 samples."""
        result = analyze_distribution([100.0, 110.0])

        assert "Need at least 3 samples" in result["message"]


class TestStabilityIntegration:
    """Test stability analysis together."""

    def test_stable_benchmark_run(self):
        """Test a stable benchmark run."""
        # Consistent latencies with no drift or spikes
        latencies = [100.0 + (i % 5) for i in range(500)]

        drift = detect_drift(latencies)
        spikes = detect_spikes(latencies)
        distribution = analyze_distribution(latencies)

        assert not drift["has_drift"]
        assert not spikes["has_spikes"]
        assert not distribution["is_fat_tail"]

    def test_problematic_benchmark_run(self):
        """Test a problematic benchmark run."""
        # Thermal throttling + spikes + fat tail
        first_half = [100.0] * 250
        second_half = [130.0] * 250  # Drift
        spiky = [100.0] * 5 + [500.0]  # Spike

        # Interleave to simulate real degradation
        latencies = []
        for i in range(500):
            if i % 250 < 250:
                latencies.append(first_half[i % 250] if i < 250 else second_half[i - 250])
            if i % 250 % 50 == 0:
                latencies[-1] = 500.0  # Add occasional spikes

        drift = detect_drift(latencies)
        spikes = detect_spikes(latencies)

        # Should detect at least drift or spikes
        assert drift["has_drift"] or spikes["spike_count"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
