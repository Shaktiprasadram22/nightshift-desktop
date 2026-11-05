#!/usr/bin/env python3
"""Run offline tests with an isolated application profile."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='nightshift-tests-') as directory:
    os.environ['NIGHTSHIFT_HOME'] = directory
    os.environ['GSETTINGS_BACKEND'] = 'memory'
    sys.path[:0] = [str(ROOT / 'src/nightshift_home'), str(ROOT)]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / 'tests')))
    raise SystemExit(not result.wasSuccessful())
