"""Publish only source-controlled project material using the user's GitHub CLI credential helper."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--message', default='Build TraceForge defensive telemetry and incident reconstruction platform')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='traceforge-publish-') as folder:
        checkout = Path(folder) / 'repo'
        remote = 'https://github.com/jeelthacker1/traceforge.git'
        git = ['git', '-c', 'credential.helper=!gh auth git-credential']
        subprocess.run(git + ['clone', remote, str(checkout)], check=True)
        for item in source.iterdir():
            if item.name in {'.git', '.env', '.venv', 'runtime', '.ruff_cache', '.pytest_cache'}:
                continue
            if item.is_dir():
                shutil.copytree(item, checkout / item.name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('node_modules', '.next', '__pycache__', '.pytest_cache', '.ruff_cache', '.env', '*.db', '*.db-*', '*.tsbuildinfo', 'test-results', 'playwright-report'))
            else:
                shutil.copy2(item, checkout / item.name)
        def run(command):
            return subprocess.run(git + command, cwd=checkout, check=True)
        run(['checkout', '-B', 'main'])
        run(['config', 'user.name', 'Jeel Thacker'])
        run(['config', 'user.email', '61545145+jeelthacker1@users.noreply.github.com'])
        run(['add', '.'])
        run(['diff', '--cached', '--stat'])
        run(['commit', '-m', args.message])
        run(['push', '-u', 'origin', 'main'])
        run(['rev-parse', 'HEAD'])


if __name__ == '__main__':
    main()
