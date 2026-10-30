"""Freeze identities and one-shot guards. Contains no economics or network code."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

from bot.forex.cftc_positioning_readiness import BASE, FREEZE, PRICE, SPEC, ROOT, require, sha, write_json

READY = BASE+'readiness_20261030/readiness.json'
MASK = BASE+'readiness_20261030/weekly_mask.json'
TEST_LOG = BASE+'readiness_20261030/tests.txt'
TEST_XML = BASE+'readiness_20261030/tests.xml'
OUTPUT = BASE+'economics_once_20261030'
SOURCES = [SPEC, 'scripts/acquire_cftc_positioning.py', 'scripts/prepare_cftc_positioning.py',
           'scripts/run_cftc_positioning.py', 'bot/forex/cftc_positioning.py',
           'bot/forex/cftc_positioning_readiness.py', 'bot/forex/cftc_positioning_binding.py',
           'tests/test_cftc_positioning.py', 'tests/test_tokyo_fix_baseline.py',
           'bot/__init__.py', 'bot/forex/__init__.py',
           'bot/forex/tokyo_fix_baseline.py', 'bot/forex/tokyo_fix_readiness.py',
           'scripts/prepare_tokyo_fix_readiness.py', 'scripts/run_tokyo_fix.py',
           'governance/2026-09-24-intraday-passive-benchmark-amendment.md',
           'provenance/tokyo_v20_daily_research_venue.md', 'pytest.ini', 'requirements.txt']
INPUTS = [PRICE, 'CLAUDE.md',
          'reports/forex/tokyo_fix/readiness_20260924/input_binding.json',
          BASE+'inputs/tff_jpy_raw.json', BASE+'inputs/acquisition.json',
          BASE+'inputs/official_notices_web_snapshot.json']
EVIDENCE = [READY, MASK, TEST_LOG, TEST_XML]


def versions():
    return {'python': platform.python_version(),
            **{p: importlib.metadata.version(p) for p in ('numpy', 'pandas', 'tzdata', 'pytest')}}


def hashes(paths, root=ROOT):
    return {p: sha(root/p) for p in paths}


def git(*args, root=ROOT):
    return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()


def verify(expected_commit, root=ROOT):
    require(len(expected_commit) == 40 and all(c in '0123456789abcdef' for c in expected_commit),
            'Require exact 40-character freeze commit')
    require(git('rev-parse', 'HEAD', root=root) == expected_commit, 'Wrong frozen HEAD')
    for p in SOURCES+[FREEZE]:
        require(git('hash-object', p, root=root) == git('rev-parse', f'HEAD:{p}', root=root),
                f'Frozen tracked file differs from commit: {p}')
    freeze = json.loads((root/FREEZE).read_text(encoding='utf-8'))
    require(set(freeze) == {'status','authorization','runtime','bindings','sample','economics_executed'},
            'Unknown/missing freeze keys')
    require(freeze['status'] == 'FROZEN_EXPLORATORY_USER_RUN_ONLY' and freeze['economics_executed'] is False,
            'Invalid freeze state')
    require(set(freeze['bindings']) == set(SOURCES+INPUTS+EVIDENCE), 'Freeze binding set changed')
    require(freeze['runtime'] == versions(), 'Runtime changed since readiness')
    require(freeze['bindings'] == hashes(SOURCES+INPUTS+EVIDENCE, root), 'Bound input/code/evidence changed')
    ready = json.loads((root/READY).read_text(encoding='utf-8'))
    require(ready['status'] == 'STRUCTURAL_READY_NO_ECONOMICS' and ready['economics_executed'] is False,
            'Invalid readiness status')
    require(ready['summary'] == freeze['sample'] and ready['tests_exit_code'] == 0,
            'Readiness/test binding mismatch')
    require(not (root/OUTPUT).exists(), 'One-shot already claimed; failed attempts remain consumed')
    return freeze


def claim(root=ROOT):
    target = root/OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)  # Atomic across simultaneous invocations, no output override.
    return target


def now():
    return datetime.now(timezone.utc).isoformat()
