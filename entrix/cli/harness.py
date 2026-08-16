"""Harness system CLI commands."""
import argparse
import json
import sys
from pathlib import Path

from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.gate.arbiter import GateEngine
from entrix.harness.conditions import WhenContext
from entrix.harness.store import EvidenceStore


def validate_command(config_path: str) -> int:
    """Validate a harness.yaml configuration.

    Args:
        config_path: Path to the harness.yaml file

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        config = load_harness_config(Path(config_path))

        print(f"✓ Valid harness configuration: {config_path}")
        print(f"  Version: {config.version}")
        print(f"  Evidence producers: {len(config.evidence_producers)}")
        print(f"  Gate policies: {len(config.gate_policies)}")

        return 0

    except Exception as e:
        print(f"✗ Invalid configuration: {e}", file=sys.stderr)
        return 1


def run_command(config_path: str, output: str) -> int:
    """Execute the harness collection and gate arbitration process.

    Args:
        config_path: Path to harness.yaml
        output: Output format ('text' or 'json')

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        config = load_harness_config(Path(config_path))
        repo_root = Path.cwd()

        # Create context
        context = HarnessRunContext(
            task_id="manual-run",
            repo_root=repo_root,
            when_context=WhenContext(repo_root=repo_root, changed_files=[], current_branch="manual"),
            store=EvidenceStore(repo_root),
        )

        # Collect evidence
        print("Collecting evidence...", file=sys.stderr)
        engine = EvidenceEngine(config)
        bundle = engine.collect(context)

        print(f"Collected {len(bundle.evidence)} evidence items", file=sys.stderr)

        # Arbitrate gates
        print("Arbitrating gates...", file=sys.stderr)
        gate_engine = GateEngine(config.gate_policies)
        verdict = gate_engine.arbitrate(bundle)

        # Output results
        if output == "json":
            result = {
                "status": verdict.status.value if hasattr(verdict.status, 'value') else verdict.status,
                "summary": verdict.summary,
                "evidence_count": len(bundle.evidence),
                "gate_results": [
                    {
                        "policy": r.policy_name,
                        "severity": r.severity.value if hasattr(r.severity, 'value') else r.severity,
                        "passed": r.passed,
                        "message": r.message,
                    }
                    for r in verdict.gate_results
                ],
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            status_value = verdict.status.value if hasattr(verdict.status, 'value') else verdict.status
            print(f"\n{'=' * 50}")
            print(f"Verdict: {str(status_value).upper()}")
            print(f"{'=' * 50}")
            print(f"Summary: {verdict.summary}")

            if verdict.gate_results:
                print(f"\nGate results:")
                for result in verdict.gate_results:
                    status_icon = "✓" if result.passed else "✗"
                    severity_value = result.severity.value if hasattr(result.severity, 'value') else result.severity
                    print(f"  {status_icon} {result.policy_name} ({severity_value}): {result.message}")

        # Exit with appropriate code
        return 0 if (verdict.status.value if hasattr(verdict.status, 'value') else verdict.status) == "pass" else 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    """CLI entry point.

    Args:
        argv: Command line arguments (uses sys.argv if None)

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="entrix harness", description="Evidence collection and gate arbitration Harness commands"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a harness.yaml configuration")
    validate_parser.add_argument("config_path", help="Path to the harness.yaml file")

    # Run command
    run_parser = subparsers.add_parser("run", help="Execute harness collection and arbitration")
    run_parser.add_argument("--config", default="harness.yaml", help="Path to harness.yaml (default: harness.yaml)")
    run_parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format (default: text)")

    args = parser.parse_args(argv)

    if args.command == "validate":
        return validate_command(args.config_path)
    elif args.command == "run":
        return run_command(args.config, args.output)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())