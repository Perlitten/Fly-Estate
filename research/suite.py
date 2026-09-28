"""Resume the R1 experiments, serially. Existing successful runs are preserved."""
import json
import subprocess
import sys
from research.bootstrap import ROOT, MANIFEST, sha256

protocols = [
    ['taste', '--trials', '3', '--seed', '0'],
    ['learning', '--seed', '0', '--gain', '20'],
    ['learning', '--seed', '1', '--gain', '20'],
    ['learning', '--seed', '2', '--gain', '20'],
    ['learning', '--seed', '0', '--gain', '1'],
    ['stability', '--scope', 'subgraph', '--seed', '0'],
    ['stability', '--scope', 'subgraph', '--stabilized', '--seed', '0'],
    ['stability', '--scope', 'full', '--seed', '0'],
]

def main():
    from research.run import arguments, run_name, environment
    for command in protocols:
        sys.argv = ['research.run', *command]
        args = arguments()
        path = ROOT / 'reports/results' / (run_name(args) + '.json')
        if path.exists():
            result = json.loads(path.read_text())
            if result['exit_code'] != 0 or result['upstream_manifest_sha256'] != sha256(MANIFEST):
                raise RuntimeError(f'Failed or stale run requires review: {path}')
            if result['environment']['packages'] != environment()['packages']:
                raise RuntimeError(f'Environment changed: {path}')
            print(f"Keeping successful run: {result['run']}", flush=True)
            continue
        print('Running: ' + ' '.join(command), flush=True)
        subprocess.run([sys.executable, '-m', 'research.run', *command], cwd=ROOT, check=True)

if __name__ == '__main__':
    main()
