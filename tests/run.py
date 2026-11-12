"""One free test command for the maintained package and its official BFCL adapter."""
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def run_tests(stream=None, verbosity=2):
    from cs769.bootstrap import ensure_bfcl
    ensure_bfcl()
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.discover(str(ROOT / "tests")),
        unittest.defaultTestLoader.loadTestsFromName("cs769.tests.test_core"),
    ])
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Tests must not use the network")):
        return unittest.TextTestRunner(stream=stream, verbosity=verbosity).run(suite)

if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(0 if run_tests().wasSuccessful() else 1)
