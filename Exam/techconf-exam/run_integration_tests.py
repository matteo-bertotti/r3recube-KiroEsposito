"""Helper script to run integration tests and write output to a file."""
import subprocess, sys, pathlib

root = pathlib.Path(__file__).parent
out_file = root / "integration_test_output.txt"

result = subprocess.run(
    [
        sys.executable, "-m", "pytest",
        "services/user-service/tests/integration/test_integration.py",
        "-v", "--tb=short",
    ],
    cwd=str(root),
    capture_output=True,
    text=True,
    timeout=90,
)

output = result.stdout + result.stderr
out_file.write_text(output, encoding="utf-8")
print(f"Exit code: {result.returncode}")
print(f"Output saved to: {out_file}")
print(output[-3000:])  # last 3000 chars to console
