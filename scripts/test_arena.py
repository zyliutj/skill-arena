"""Synthetic checks; all outputs stay in data/tmp and never enter real history."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('arena', Path(__file__).with_name('arena.py'))
arena = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arena)


class ArenaTest(unittest.TestCase):
    def setUp(self):
        temp = Path(__file__).resolve().parents[1] / 'data' / 'tmp'
        temp.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp)
        self.root = Path(self.tmp.name)
        arena.init(self.root)
        self.run = arena.new_run(self.root, 'test')

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self):
        manifest = []
        for name in ('one', 'two', 'failed'):
            folder = self.run / 'variants' / name
            folder.mkdir()
            (folder / 'answer.md').write_text('synthetic <script>alert(1)</script>', encoding='utf-8')
            manifest.append({'id': name, 'artifacts': ['answer.md']})
        mapping = arena.packet(self.run, manifest)
        rows = []
        for alias, item in mapping.items():
            failed = item['id'] == 'failed'
            score = 4 if item['id'] == 'one' else 3.9
            rows.append({'id': alias, 'status': 'failed' if failed else 'eligible', 'dimensions': {} if failed else {k: {'score': score, 'evidence': 'answer.md: synthetic evidence'} for k in arena.read(self.run / 'rubric.json')['weights']}, **{k: '<script>test</script>' for k in ('summary', 'strengths', 'weaknesses', 'best_for', 'uncertainty')}})
        arena.write(self.run / 'evaluation' / 'judge.json', {'results': rows})
        return rows

    def test_report_tie_failure_escape(self):
        self.fixture()
        rows = arena.report(self.run)
        self.assertEqual([r['rank'] for r in rows], [1, 1, None])
        self.assertEqual(rows[0]['total'], 80)
        page = (self.run / 'report.html').read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>', page)
        self.assertIn('file:', page)

    def test_omission_and_invalid_scores(self):
        rows = self.fixture()
        path = self.run / 'evaluation' / 'judge.json'
        arena.write(path, {'results': rows[:-1]})
        with self.assertRaises(ValueError): arena.report(self.run)
        for r in rows:
            if r['status'] == 'eligible':
                next(iter(r['dimensions'].values()))['score'] = float('nan')
                break
        arena.write(path, {'results': rows})
        with self.assertRaises(ValueError): arena.report(self.run)

    def test_paths_snapshot_and_registry(self):
        with self.assertRaises(ValueError): arena.safe_child(self.root, '../escape')
        with self.assertRaises(ValueError): arena.new_run(self.root, 'CON')
        source = self.root / 'source'
        source.mkdir()
        (source / 'SKILL.md').write_text('test', encoding='utf-8')
        arena.snapshot(self.run, 'sample', source)
        self.assertIn('SKILL.md', arena.read(self.run / 'snapshots' / 'sample.manifest.json')['files'])
        with self.assertRaises(FileExistsError): arena.snapshot(self.run, 'sample', source)
        rec = dict(id='sample', name='Sample', source='local', version='1', tags=['test'], local_path=str(source), license='test')
        arena.register(self.root, rec)
        arena.register(self.root, dict(rec, version='2'))
        self.assertEqual(len(arena.read(self.root / 'registry.json')['skills']), 1)


if __name__ == '__main__':
    unittest.main()
