"""Run offline regression tests with no dependency on personal runtime state."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'manual_launcher'),str(ROOT/'ok-wuthering-waves-3.7.8')]
(ROOT/'local-runs').mkdir(exist_ok=True)
if __name__=='__main__':
    suite=unittest.defaultTestLoader.discover(str(ROOT/'manual_launcher'),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
