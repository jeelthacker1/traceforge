"""Run checks in a temporary directory when the host workspace is read-only to child processes."""
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(args, cwd, env=None):
    print('RUN ' + ' '.join(map(str, args)), flush=True)
    result = subprocess.run(args, cwd=cwd, env=env)
    print('EXIT ' + str(result.returncode), flush=True)
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['backend', 'web'])
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='traceforge-validate-') as folder:
        root = Path(folder) / 'project'
        shutil.copytree(source, root, ignore=shutil.ignore_patterns('node_modules', '.venv', '.next', '__pycache__', '.git', 'runtime'))
        if args.mode == 'backend':
            deps = Path(folder) / 'deps'
            if run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--target', str(deps), '-r', str(root / 'backend/requirements.txt')], root):
                return 1
            env = {**os.environ, 'PYTHONPATH': str(deps), 'PYTHONUTF8': '1'}
            codes = [run([sys.executable, '-m', 'ruff', 'check', '.'], root / 'backend', env), run([sys.executable, '-m', 'pytest', '-q'], root / 'backend', env)]
            if not any(codes):
                codes.append(run([sys.executable, 'benchmark.py'], root / 'backend', env))
            return int(any(codes))
        node = shutil.which('node')
        npm = Path(node).parent / 'node_modules/npm/bin/npm-cli.js'
        web = root / 'web'
        if run([node, str(npm), 'install', '--fetch-retries=1', '--fetch-timeout=30000'], web):
            return 1
        codes = [run([node, str(npm), 'run', 'build'], web), run([node, str(npm), 'run', 'typecheck'], web)]
        print('ARTIFACT_PACKAGE_LOCK=' + base64.b64encode((web / 'package-lock.json').read_bytes()).decode(), flush=True)
        return int(any(codes))


if __name__ == '__main__':
    sys.exit(main())
