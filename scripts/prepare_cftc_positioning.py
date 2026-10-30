"""Metadata-only readiness and synthetic tests. Never calls the economics module."""
import json
import subprocess
import sys

from bot.forex.cftc_positioning_readiness import ROOT, FREEZE, readiness, require, write_json
from bot.forex.cftc_positioning_binding import (READY, MASK, TEST_LOG, TEST_XML, SOURCES, INPUTS,
                                              EVIDENCE, hashes, versions)


def main():
    require(not (ROOT/FREEZE).exists(), 'Freeze already exists; no silent re-freeze')
    directory = (ROOT/READY).parent
    directory.mkdir(parents=True, exist_ok=False)
    result = readiness()
    write_json(ROOT/MASK, result.pop('mask'))
    command = [sys.executable, '-m', 'pytest', 'tests/test_cftc_positioning.py',
               'tests/test_tokyo_fix_baseline.py', '-q', '--junitxml='+str(ROOT/TEST_XML)]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (ROOT/TEST_LOG).write_text(tests.stdout+'\n'+tests.stderr, encoding='utf-8')
    require(tests.returncode == 0, 'Focused synthetic tests failed; see tests.txt')
    result.update(tests_exit_code=tests.returncode, test_command=command, runtime=versions(),
                  inputs=hashes(INPUTS), sources=hashes(SOURCES),
                  seal_access=False, strategy_economics_executed=False)
    write_json(ROOT/READY, result)
    write_json(ROOT/FREEZE, {
        'status': 'FROZEN_EXPLORATORY_USER_RUN_ONLY',
        'authorization': 'User gate CFTC_POSITIONING_EXPLORATORY_FREEZE_AND_RUNNER; economics not run by agent',
        'runtime': versions(), 'bindings': hashes(SOURCES+INPUTS+EVIDENCE),
        'sample': result['summary'], 'economics_executed': False})
    print(json.dumps({'status': result['status'], 'summary': result['summary'], 'freeze': FREEZE}))


if __name__ == '__main__':
    main()
