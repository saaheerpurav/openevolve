"""
Subprocess entry point for sandboxed TDES test execution.

Invoked as ``python -m openevolve.tdes._runner <suite_file> <modules_dir>
<out_json>``. Imports the candidate codebase from ``modules_dir`` and runs the
suite defined in ``suite_file``, writing per-test results as JSON to
``out_json``. Running in a fresh process isolates candidate crashes/hangs from
the controller (the parent enforces the timeout).
"""

import json
import sys

from openevolve.tdes.test_suite import (
    TDESTestSuite,
    _execute_tests,
    _import_codebase,
)


def main(argv) -> int:
    if len(argv) != 3:
        print("usage: _runner <suite_file> <modules_dir> <out_json>", file=sys.stderr)
        return 2
    suite_file, modules_dir, out_path = argv

    suite = TDESTestSuite.load_from_file(suite_file)
    imported = _import_codebase(modules_dir, suite.module_names)
    results = _execute_tests(suite, imported)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
