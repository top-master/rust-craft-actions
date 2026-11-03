"""The opt-in `cargo prepare` step that writes an app's generated sources before a build."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = 'actions/cargo-prepare'


def load(path):
    return yaml.load((ROOT / path).read_text(), Loader=yaml.BaseLoader)


def workflow(name):
    return load(Path('.github/workflows') / name)


def index_of(steps, needle):
    return next((i for i, step in enumerate(steps) if needle in step.get('uses', '')), None)


class CargoPrepareWorkflowTests(unittest.TestCase):
    def test_every_build_job_prepares_after_the_rust_cache(self):
        for name in ('release.yml', 'windows-arm64.yml'):
            for job, data in workflow(name)['jobs'].items():
                steps = data.get('steps', [])
                if index_of(steps, 'rust-toolchain') is None:
                    continue
                with self.subTest(workflow=name, job=job):
                    prepare = index_of(steps, ACTION)
                    self.assertIsNotNone(prepare, f'{name}: {job} builds without cargo prepare')
                    self.assertGreater(prepare, index_of(steps, 'rust-cache'))

    def test_the_gate_prepares_before_it_runs(self):
        for job, data in workflow('gate.yml')['jobs'].items():
            steps = data.get('steps', [])
            gate = next((i for i, step in enumerate(steps) if step.get('name') == 'Gate'), None)
            if gate is None:
                continue
            with self.subTest(job=job):
                prepare = index_of(steps, ACTION)
                self.assertIsNotNone(prepare)
                self.assertLess(prepare, gate)


class CargoPrepareActionTests(unittest.TestCase):
    RUN = load(Path(ACTION) / 'action.yml')['runs']['steps'][0]['run']

    def run_with_cargo_list(self, listing):
        """Runs the action's script with a fake `cargo` whose `--list` prints `listing`."""
        with tempfile.TemporaryDirectory() as tmp:
            cargo = Path(tmp) / 'cargo'
            cargo.write_text('#!/bin/bash\n'
                             'if [ "$1" = --list ]; then printf "%s\\n" "$LISTING"; exit 0; fi\n'
                             'echo "ran cargo $*"\n')
            cargo.chmod(0o755)
            env = {**os.environ, 'PATH': f'{tmp}:{os.environ["PATH"]}', 'LISTING': listing}
            return subprocess.run(['bash', '-eo', 'pipefail', '-c', self.RUN], cwd=tmp,
                                  capture_output=True, text=True, env=env)

    def test_runs_the_alias_when_the_app_defines_it(self):
        result = self.run_with_cargo_list('Installed Commands:\n    build\n    prepare              alias: xtask prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ran cargo prepare', result.stdout)

    def test_does_nothing_without_the_alias(self):
        result = self.run_with_cargo_list('Installed Commands:\n    build\n    preparex             alias: run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('ran cargo', result.stdout)


if __name__ == '__main__':
    unittest.main()
