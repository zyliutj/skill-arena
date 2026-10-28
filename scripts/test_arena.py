"""Synthetic checks; all outputs stay in data/tmp and never enter real history."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('arena', Path(__file__).with_name('arena.py'))
arena = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arena)


class ArenaTest(unittest.TestCase):
    def test_comparison_limit_and_fixed_baselines(self):
        items = [{'id':'plain','kind':'baseline'}, {'id':'mixed','kind':'mixed-baseline'}, {'id':'first'}, {'id':'second'}]
        arena.validate_comparison(items, 'full')
        with self.assertRaises(ValueError): arena.validate_comparison(items + [{'id':'extra'}], 'full')
        with self.assertRaises(ValueError): arena.validate_comparison(items[1:], 'full')
        arena.validate_comparison(items[2:3], 'followup')

    def test_numbering_survives_anonymization_and_ranking(self):
        self.fixture()
        mapping = arena.read(self.run/'mapping.json')
        self.assertEqual({x['id']:x['scheme_number'] for x in mapping.values()}, {'one':1,'two':2,'failed':3})
        arena.report(self.run)
        ui = arena.read(self.run/'interaction.json')
        page = (self.run/'report.html').read_text(encoding='utf-8')
        for c in ui['candidates']:
            n = {'one':1,'two':2,'failed':3}[c['variant_id']]
            self.assertTrue(c['label'].startswith('方案'+str(n)+' · '))
            self.assertIn('方案'+str(n)+' · '+c['variant_id'], page)

    def test_mixed_members_require_distinct_eligible_skills(self):
        members = [{'id': x, 'stars_status': 'known', 'stars': 500,
                    'stars_checked_at': '2026-10-26'} for x in ('one', 'two')]
        record = {'kind': 'mixed-baseline', 'members': members}
        self.assertTrue(arena.selection_gate(record)['eligible'])
        members[1]['stars'] = 499
        self.assertFalse(arena.selection_gate(record)['eligible'])
        members[1].update(user_specified=True, user_specified_evidence='Named by user')
        self.assertTrue(arena.selection_gate(record)['eligible'])
        record['members'] = members[:1]
        self.assertFalse(arena.selection_gate(record)['eligible'])
        record['members'] = [members[0], members[0]]
        self.assertFalse(arena.selection_gate(record)['eligible'])

    def test_mixed_label_removal_and_continuation(self):
        self.fixture()
        mapping = arena.read(self.run / 'mapping.json')
        item = next(x for x in mapping.values() if x['id'] == 'one')
        item.update(kind='mixed-baseline', members=[{'id':'first'},{'id':'second'}])
        arena.write(self.run / 'mapping.json', mapping)
        arena.report(self.run)
        self.assertEqual(arena.candidate_label(item), '方案1 · 多 skill 协作基线')
        with self.assertRaises(ValueError): arena.lowest_two(self.run)
        child = arena.followup(self.root, 'test', 'next', {'mode':'continue', 'variants':['one'], 'instruction':'Next task'})
        parent = arena.read(child / 'lineage.json')['parents'][0]
        self.assertEqual(parent['members'], item['members'])
        self.assertIn('多 skill 协作基线', (self.run/'report.html').read_text(encoding='utf-8'))

    def test_stars_gate_boundary_and_user_exception(self):
        record = {'id': 'candidate', 'status': 'selected', 'source': 'https://github.com/example/repo',
                  'stars_status': 'known', 'stars': 499, 'stars_checked_at': '2026-10-23'}
        self.assertFalse(arena.selection_gate(record)['eligible'])
        path = self.root / 'discovery.json'
        arena.write(path, {'candidates': [record]})
        with self.assertRaises(ValueError): arena.check_selection(path)
        record['stars'] = 500
        self.assertTrue(arena.selection_gate(record)['eligible'])
        record.update(stars=0, user_specified=True, user_specified_evidence='User explicitly requested this project')
        arena.write(path, {'candidates': [record]})
        self.assertEqual(arena.check_selection(path)['status'], 'passed')
        record.pop('user_specified_evidence')
        with self.assertRaises(ValueError): arena.selection_gate(record)

    def test_stars_gate_unknown_and_not_applicable(self):
        self.assertFalse(arena.selection_gate({'stars_status': 'unknown'})['eligible'])
        self.assertTrue(arena.selection_gate({'stars_status': 'not_applicable', 'source': 'local'})['eligible'])
        self.assertFalse(arena.selection_gate({'stars_status': 'not_applicable', 'source': 'https://github.com/example/repo'})['eligible'])
        self.assertTrue(arena.selection_gate({'stars_status': 'unknown', 'user_specified': True,
                         'user_specified_evidence': 'Explicit continuation request'})['eligible'])

    def test_selection_priority_missing_and_log_stars(self):
        record = {'scores': {k: 4 for k in ('task_fit', 'workflow', 'compatibility', 'maintenance')}}
        self.assertEqual(arena.selection_priority(record)['total'], 80)
        self.assertTrue(arena.selection_priority(record)['provisional'])
        record['stars_status'] = 'not_applicable'
        self.assertFalse(arena.selection_priority(record)['provisional'])
        record.update(stars_status='known', stars=999, stars_checked_at='2026-10-21')
        self.assertEqual(arena.selection_priority(record)['total'], 77)
        for stars in (-1, True, 1.5):
            record['stars'] = stars
            with self.assertRaises(ValueError): arena.selection_priority(record)

    def test_toolkit_overview_does_not_change_judging_or_leak_into_packet(self):
        self.fixture()
        before = arena.report(self.run)
        metadata = {'id': 'one', 'candidate_type': 'toolkit', 'source': 'https://github.com/example/toolkit',
                    'repository': 'example/toolkit', 'version': 'fixed-sha', 'reason': '<script>bad</script>',
                    'stars_status': 'known', 'stars': 99999, 'stars_checked_at': '2026-10-21',
                    'scores': {k: 5 for k in ('task_fit', 'workflow', 'compatibility', 'maintenance')}}
        arena.write(self.run / 'discovery.json', {'candidates': [metadata]})
        arena.write(self.run / 'variants' / 'one' / 'execution.json', {'modules_used': ['planning']})
        after = arena.report(self.run)
        self.assertEqual(before, after)
        page = (self.run / 'report.html').read_text(encoding='utf-8')
        self.assertIn('toolkit', page)
        self.assertIn('planning', page)
        self.assertIn('99999', page)
        self.assertIn('未记录', page)
        self.assertEqual(page.count('<script>'), 1)
        self.assertNotIn('<script>alert', page)
        self.assertNotIn('<script>test', page)
        self.assertFalse(any(p.name in {'discovery.json', 'execution.json'} for p in (self.run / 'judge-packet').rglob('*')))

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
        self.assertEqual(page.count('<script>'), 1)
        self.assertNotIn('<script>alert', page)
        self.assertNotIn('<script>test', page)
        self.assertIn('data:application/octet-stream;base64,', page)
        self.assertIn('synthetic &lt;script&gt;alert(1)', page)

    def test_reader_complete_contents_order_and_sidecar(self):
        self.fixture()
        before = arena.report(self.run)
        original = '# Title\n## Main\n- Item\n\n| Field | Value |\n|---|---|\n| End | FULL-END-MARKER |\n[jump](javascript:alert)'
        answer = self.run / 'variants' / 'one' / 'answer.md'
        answer.write_text(original, encoding='utf-8')
        arena.write(self.run / 'presentation.json', {'candidates': {'one': {
            'metadata': {'description': 'Simple description', 'project_updated_at': '2026-10-22'},
            'diagrams': [{'title': 'Flow', 'steps': ['Read', 'Plan'], 'source': 'answer.md Main'}]}}})
        self.assertEqual(before, arena.report(self.run))
        page = (self.run / 'report.html').read_text(encoding='utf-8')
        self.assertIn('FULL-END-MARKER', page)
        self.assertIn('<ul><li>Item</li></ul>', page)
        self.assertIn('<thead>', page)
        self.assertIn('Simple description', page)
        self.assertIn('answer.md Main', page)
        self.assertNotIn('href="javascript:', page)
        self.assertNotIn('<script src=', page)
        self.assertLess(page.index('id="candidate-one"'), page.index('id="evaluation"'))
        self.assertIn('data-toggle="close"', page)
        self.assertEqual(answer.read_text(encoding='utf-8'), original)

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
        self.assertIn('先保留 方案1 · one', page)
        ui = arena.read(self.run / 'interaction.json')
        self.assertEqual(ui['candidates'][0]['variant_id'], 'one')
        self.assertTrue(ui['selection']['questions'][0]['options'][0].startswith('方案1 · one — '))

    def test_adjust_add_and_remove_preserves_originals(self):
        self.fixture()
        child = arena.followup(self.root, 'test', 'adjusted',
                               {'mode': 'adjust', 'add_count': 2, 'remove': ['two']})
        lineage = arena.read(child / 'lineage.json')
        self.assertEqual(set(lineage['variants']), {'one', 'failed'})
        self.assertEqual(lineage['removed_variants'], ['two'])
        self.assertEqual(lineage['add_count'], 2)
        self.assertEqual(lineage['status'], 'discovery-required')
        self.assertFalse(lineage['inherit_previous_answers'])
        self.assertTrue(all(b['artifacts'] == [] for b in lineage['parents']))
        self.assertTrue((self.run / 'variants' / 'two' / 'answer.md').exists())
        self.assertEqual(arena.read(self.run / 'state.json')['selected'], [])

    def test_adjust_only_remove_and_replace_all(self):
        self.fixture()
        child = arena.followup(self.root, 'test', 'reduced',
                               {'mode': 'adjust', 'add_count': 0, 'remove': ['two']})
        self.assertEqual(arena.read(child / 'lineage.json')['status'], 'handoff-required')
        req = arena.resolve_feedback(self.root, 'test',
              {'mode': 'adjust', 'add_count': 2, 'remove': ['one', 'two', 'failed']})
        self.assertEqual(req['variants'], [])
        for rec in [
            {'mode': 'adjust', 'add_count': 0},
            {'mode': 'adjust', 'add_count': 0, 'remove': ['one', 'two', 'failed']},
            {'mode': 'adjust', 'remove': ['missing']},
            {'mode': 'adjust', 'remove': ['one', 'one']},
            {'mode': 'adjust', 'add_count': True},
            {'mode': 'adjust', 'variants': ['one']},
        ]:
            with self.assertRaises(ValueError):
                arena.followup(self.root, 'test', 'invalid-adjustment', rec)
            self.assertFalse((self.root / 'runs' / 'invalid-adjustment').exists())

    def test_lowest_two_excludes_baseline_and_requires_clear_cutoff(self):
        mapping = {k: {'id': n, 'artifacts': [], 'kind': kind}
                   for k, n, kind in [('A', 'one', 'skill'), ('B', 'two', 'skill'),
                                     ('C', 'three', 'skill'), ('D', 'control', 'baseline'),
                                     ('E', 'failed', 'skill')]}
        arena.write(self.run / 'mapping.json', mapping)
        rows = [{'id': k, 'status': 'eligible' if k != 'E' else 'failed', 'total': score}
                for k, score in [('A', 40), ('B', 50), ('C', 80), ('D', 1), ('E', None)]]
        arena.write(self.run / 'ranking.json', {'results': rows})
        self.assertEqual(arena.lowest_two(self.run), ['one', 'two'])
        request = arena.resolve_feedback(self.root, 'test',
                                         {'mode': 'adjust', 'remove': 'lowest-two'})
        self.assertEqual(request['removed_variants'], ['one', 'two'])
        rows[2]['total'] = 52
        arena.write(self.run / 'ranking.json', {'results': rows})
        with self.assertRaises(ValueError): arena.lowest_two(self.run)
        rows[1]['status'] = rows[2]['status'] = 'needs-review'
        arena.write(self.run / 'ranking.json', {'results': rows})
        with self.assertRaises(ValueError): arena.lowest_two(self.run)

    def test_interaction_uses_names_and_composable_adjustment(self):
        self.fixture()
        mapping = arena.read(self.run / 'mapping.json')
        for item in mapping.values():
            item['display_name'] = 'Real skill ' + item['id']
        arena.write(self.run / 'mapping.json', mapping)
        arena.report(self.run)
        ui = arena.read(self.run / 'interaction.json')
        self.assertEqual(len(ui['adjustment']['questions']), 2)
        self.assertEqual(set(ui['lowest_two']), {'one', 'two'})
        self.assertTrue(all(c['label'].startswith('方案') and 'Real skill ' in c['label'] for c in ui['candidates']))
        self.assertIn('Real skill one', ui['adjustment']['questions'][1]['options'][2])


if __name__ == '__main__':
    unittest.main()
