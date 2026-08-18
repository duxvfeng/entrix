"""Test that fitness report serialization works correctly."""
import json
from dataclasses import dataclass
from enum import Enum

from entrix.harness.producers.builtin import _serialize_for_json
from entrix.model import Tier, MetricResult, DimensionScore, FitnessReport


def test_serialize_tier_enum():
    """Test that Tier enum is serialized to its string value."""
    result = MetricResult(
        metric_name="test",
        tier=Tier.FAST,
        passed=True,
        output="success"
    )
    serialized = _serialize_for_json(result)
    assert serialized["tier"] == "fast"
    assert serialized["metric_name"] == "test"

    # Should be JSON serializable
    json_str = json.dumps(serialized)
    assert '"tier": "fast"' in json_str
    print("[OK] Tier enum serialization works")


def test_serialize_fitness_report():
    """Test that FitnessReport with nested enums serializes correctly."""
    report = FitnessReport(
        dimensions=[
            DimensionScore(
                dimension="code_quality",
                weight=50,
                passed=5,
                total=10,
                score=50.0,
                results=[
                    MetricResult(
                        metric_name="lint",
                        tier=Tier.FAST,
                        passed=True,
                        output="ok"
                    ),
                    MetricResult(
                        metric_name="test",
                        tier=Tier.NORMAL,
                        passed=False,
                        output="failed"
                    ),
                ]
            )
        ],
        final_score=50.0,
        hard_gate_blocked=False,
        score_blocked=True
    )

    serialized = _serialize_for_json(report)

    # Check enum serialization
    assert serialized["dimensions"][0]["results"][0]["tier"] == "fast"
    assert serialized["dimensions"][0]["results"][1]["tier"] == "normal"

    # Should be JSON serializable
    json_str = json.dumps(serialized)
    assert json_str is not None
    print("[OK] FitnessReport serialization works")


if __name__ == "__main__":
    test_serialize_tier_enum()
    test_serialize_fitness_report()
    print("\nAll serialization tests passed!")
