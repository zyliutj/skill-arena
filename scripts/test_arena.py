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

    def test_selection_and_multi_branch_continuation(self):
        self.fixture()
        original = (self.run / 'variants' / 'one' / 'answer.md').read_bytes()
        arena.feedback(self.root, 'test', {'mode': 'select', 'variants': ['one', 'two'],
                                         'user_message': 'Keep these two'})
        child = arena.followup(self.root, 'test', 'next',
                               {'mode': 'continue', 'instruction': 'Design experiments'})
        lineage = arena.read(child / 'lineage.json')
        self.assertEqual(lineage['variants'], ['one', 'two'])
        self.assertEqual(lineage['parent_run_id'], 'test')
        for branch in lineage['parents']:
            self.assertEqual(len(branch['artifacts']), 1)
            self.assertIn('/' + branch['variant_id'] + '/', branch['artifacts'][0]['path'])
            self.assertEqual(len(branch['artifacts'][0]['sha256']), 64)
        self.assertEqual((child / 'task.md').read_text(encoding='utf-8').strip(), 'Design experiments')
        self.assertEqual(arena.read(child / 'protocol.json')['status'], 'draft')
        self.assertEqual((self.run / 'variants' / 'one' / 'answer.md').read_bytes(), original)
        self.assertFalse((child / 'state.json').exists())
        with self.assertRaises(FileExistsError):
            arena.followup(self.root, 'test', 'next', {'mode': 'redo', 'variants': ['one']})

    def test_refine_preserves_rubric_and_selection(self):
        self.fixture()
        arena.feedback(self.root, 'test', {'mode': 'select', 'variants': ['one']})
        child = arena.followup(self.root, 'test', 'revision',
                               {'mode': 'refine', 'variants': ['two'], 'instruction': 'Add sources'})
        self.assertEqual(arena.read(child / 'rubric.json'), arena.read(self.run / 'rubric.json'))
        self.assertEqual(arena.read(self.run / 'state.json')['selected'], ['one'])
        self.assertEqual(arena.read(child / 'lineage.json')['variants'], ['two'])
        self.assertIn('Add sources', (child / 'task.md').read_text(encoding='utf-8'))

    def test_redo_all_does_not_inherit_answers(self):
        self.fixture()
        (self.run / 'variants' / 'one' / 'answer.md').unlink()
        child = arena.followup(self.root, 'test', 'redo', {'mode': 'redo', 'variants': 'all'})
        lineage = arena.read(child / 'lineage.json')
        self.assertEqual(set(lineage['variants']), {'one', 'two', 'failed'})
        self.assertFalse(lineage['inherit_previous_answers'])
        self.assertTrue(all(b['artifacts'] == [] for b in lineage['parents']))

    def test_invalid_followups_leave_no_child(self):
        self.fixture()
        for record in [
            {'mode': 'continue', 'instruction': 'Next'},
            {'mode': 'refine', 'variants': ['one']},
            {'mode': 'redo', 'variants': ['unknown']},
            {'mode': 'redo', 'variants': ['one', 'one']},
            {'mode': 'refine', 'variants': 'all', 'instruction': 'More'},
            {'mode': 'select', 'variants': ['one']},
            {'mode': 'redo', 'variants': ['../escape']},
        ]:
            with self.assertRaises(ValueError):
                arena.followup(self.root, 'test', 'invalid', record)
            self.assertFalse((self.root / 'runs' / 'invalid').exists())
        self.assertFalse((self.run / 'feedback').exists())

    def test_single_result_is_quality_check_not_winner(self):
        rows = self.fixture()
        mapping = arena.read(self.run / 'mapping.json')
        alias = next(k for k, v in mapping.items() if v['id'] == 'one')
        arena.write(self.run / 'mapping.json', {alias: mapping[alias]})
        arena.write(self.run / 'evaluation' / 'judge.json',
                    {'results': [r for r in rows if r['id'] == alias]})
        result = arena.report(self.run)
        self.assertIsNone(result[0]['rank'])
        page = (self.run / 'report.html').read_text(encoding='utf-8')
        self.assertIn('方案质量检查', page)
        self.assertIn('先保留 ' + alias, page)


if __name__ == '__main__':
    unittest.main()
