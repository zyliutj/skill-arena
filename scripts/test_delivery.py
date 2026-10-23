"""Delivery invariants; synthetic files only, no live SSH or user data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil
import arena
import delivery


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'data'/'tmp'
        root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=root)
        self.root=Path(self.tmp.name).resolve()
        arena.init(self.root/'data'); self.run=arena.new_run(self.root/'data','sample')
        folder=self.run/'variants'/'sample'; folder.mkdir()
        (folder/'answer.md').write_text('# Complete answer\nEND-OF-NARRATIVE',encoding='utf-8')
        (folder/'large.bin').write_bytes(b'x'*(delivery.LIMIT+1))
        mapping=arena.packet(self.run,[{'id':'sample','artifacts':['answer.md','large.bin']}])
        alias=next(iter(mapping))
        dims={k:{'score':4,'evidence':'answer.md'} for k in arena.read(self.run/'rubric.json')['weights']}
        arena.write(self.run/'evaluation'/'judge.json',{'results':[{'id':alias,'status':'eligible','dimensions':dims,**{k:'evidence' for k in ['summary','strengths','weaknesses','best_for','uncertainty']}}]})
        arena.report(self.run)
        self.bundle=self.root/'bundle'; self.dest=self.root/'client'

    def tearDown(self): self.tmp.cleanup()

    def test_detection_uncertainty_and_explicit_context(self):
        self.assertEqual(delivery.detect(environ={})['location'],'unknown')
        self.assertEqual(delivery.detect(environ={'SSH_CLIENT':'private'})['location'],'remote')
        self.assertNotIn('private',str(delivery.detect(environ={'SSH_CLIENT':'private'})))
        self.assertEqual(delivery.detect('local',{})['location'],'local')

    def test_export_complete_narrative_and_optional_binary(self):
        before=delivery.digest(self.run/'variants'/'sample'/'answer.md')
        result=delivery.export(self.run,self.bundle)
        page=(self.bundle/'report.html').read_text(encoding='utf-8')
        self.assertIn('END-OF-NARRATIVE',page)
        self.assertIn('尚未同步',page)
        self.assertLess((self.bundle/'report.html').stat().st_size,100000)
        self.assertEqual([x['included'] for x in result['artifacts']],[False,False])
        self.assertFalse((self.bundle/'variants'/'sample'/'large.bin').exists())
        self.assertFalse((self.bundle/'snapshots').exists())
        self.assertEqual([x['path'] for x in result['files']], ['report.html'])
        self.assertNotIn('href="variants/', page)
        self.assertEqual(before,delivery.digest(self.run/'variants'/'sample'/'answer.md'))
        full=delivery.export(self.run,self.root/'full',full=True)
        self.assertTrue(all(x['included'] for x in full['artifacts']))
        with self.assertRaises(FileExistsError): delivery.export(self.run,self.bundle)

    def test_sync_retry_and_no_overwrite(self):
        delivery.export(self.run,self.bundle)
        first=delivery.sync(self.bundle,self.dest)
        self.assertEqual(first['copied'][0],'report.html')
        second=delivery.sync(self.bundle,self.dest)
        self.assertFalse(second['copied'])
        self.assertEqual(second['skipped'],first['copied'])
        (self.dest/'report.html').write_text('user edit',encoding='utf-8')
        with self.assertRaises(FileExistsError): delivery.sync(self.bundle,self.dest)
        self.assertEqual((self.dest/'report.html').read_text(),'user edit')

    def test_corruption_and_escape_rejected(self):
        delivery.export(self.run,self.bundle)
        original=(self.bundle/'report.html').read_bytes()
        (self.bundle/'report.html').write_bytes(b'corrupt')
        with self.assertRaises(ValueError): delivery.sync(self.bundle,self.dest)
        self.assertFalse(self.dest.exists())
        (self.bundle/'report.html').write_bytes(original)
        m=delivery.read(self.bundle/'delivery.json');m['files'][0]['path']='../outside'
        delivery.write(self.bundle/'delivery.json',m)
        with self.assertRaises(ValueError): delivery.sync(self.bundle,self.dest)
        with self.assertRaises(ValueError): delivery.child(self.root,'../escape')

    def test_pull_report_arrives_before_attachments(self):
        delivery.export(self.run,self.bundle,full=True)
        calls=[]
        def transfer(args,**kwargs):
            self.assertIn('StrictHostKeyChecking=yes',args[5])
            rel=args[-2].split('/bundle/',1)[1]; calls.append(rel)
            if rel.startswith('variants/'):
                self.assertTrue((self.dest/'report.html').exists())
                self.assertEqual(delivery.read(self.dest/'delivery-progress.json')['status'],'report-ready')
            shutil.copyfile(self.bundle/rel,Path(args[-1]))
        with patch('delivery.POSIX_CLIENT',True), patch('delivery.shutil.which',return_value='/usr/bin/rsync'), patch('delivery.subprocess.run',side_effect=transfer):
            result=delivery.pull('server','/bundle',self.dest)
        self.assertEqual(calls[:2],['delivery.json','report.html'])
        self.assertEqual(result['status'],'verified')
        self.assertEqual(delivery.read(self.dest/'delivery-progress.json')['status'],'verified')

    def test_default_pull_fetches_only_report_and_control_manifest(self):
        delivery.export(self.run,self.bundle)
        calls=[]
        def transfer(args,**kwargs):
            rel=args[-2].split('/bundle/',1)[1]; calls.append(rel)
            shutil.copyfile(self.bundle/rel,Path(args[-1]))
        with patch('delivery.POSIX_CLIENT',True), patch('delivery.shutil.which',return_value='/usr/bin/rsync'), patch('delivery.subprocess.run',side_effect=transfer):
            receipt=delivery.pull('server','/bundle',self.dest)
        self.assertEqual(calls,['delivery.json','report.html'])
        self.assertEqual(receipt['copied'] + receipt['skipped'], ['report.html'])
        self.assertFalse((self.dest/'variants').exists())

    def test_local_verification_requires_actual_client(self):
        manifest=delivery.export(self.run,self.bundle)
        delivery.sync(self.bundle,self.dest)
        sha=manifest['files'][0]['sha256']
        with patch('delivery.socket.gethostname',return_value='remote-server'):
            with self.assertRaises(ValueError): delivery.verify_local(self.dest,sha,'user-laptop')
        self.assertEqual(delivery.read(self.dest/'local-verification.json')['status'],'failed')
        with patch('delivery.socket.gethostname',return_value='user-laptop'):
            proof=delivery.verify_local(self.dest,sha,'user-laptop')
        self.assertEqual(proof['status'],'local-verified')
        self.assertEqual(proof['sha256'],sha)

    def test_local_verification_rechecks_modified_or_missing_report(self):
        manifest=delivery.export(self.run,self.bundle)
        delivery.sync(self.bundle,self.dest)
        sha=manifest['files'][0]['sha256']; host=delivery.socket.gethostname()
        delivery.verify_local(self.dest,sha,host)
        (self.dest/'report.html').write_text('stale or changed report',encoding='utf-8')
        with self.assertRaises(ValueError): delivery.verify_local(self.dest,sha,host)
        self.assertEqual(delivery.read(self.dest/'local-verification.json')['status'],'failed')
        (self.dest/'report.html').unlink()
        with self.assertRaises(ValueError): delivery.verify_local(self.dest,sha,host)
        self.assertEqual(delivery.read(self.dest/'local-verification.json')['status'],'failed')

    def test_preferences_separate_clients(self):
        delivery.configure(self.root,'laptop','D:/Research')
        delivery.configure(self.root,'desktop','/home/user/results')
        prefs=delivery.read(self.root/'delivery-preferences.json')
        self.assertEqual(prefs['clients']['laptop']['local_root'],'D:/Research')
        self.assertEqual(len(prefs['clients']),2)
        with self.assertRaises(ValueError): delivery.configure(self.root,'bad','relative')

    def test_pull_interruption_retains_report_and_retries(self):
        delivery.export(self.run,self.bundle,full=True)
        fail=[True]
        def transfer(args,**kwargs):
            rel=args[-2].split('/bundle/',1)[1]
            if rel.startswith('variants/') and fail[0]:
                fail[0]=False
                raise TimeoutError('simulated interruption')
            shutil.copyfile(self.bundle/rel,Path(args[-1]))
        with patch('delivery.POSIX_CLIENT',True), patch('delivery.shutil.which',return_value='/usr/bin/rsync'), patch('delivery.subprocess.run',side_effect=transfer):
            with self.assertRaises(TimeoutError): delivery.pull('server','/bundle',self.dest)
            self.assertTrue((self.dest/'report.html').exists())
            self.assertFalse((self.dest/'delivery-receipt.json').exists())
            self.assertEqual(delivery.pull('server','/bundle',self.dest)['status'],'verified')

    def test_no_channel_and_unsafe_host(self):
        with patch('delivery.shutil.which',return_value=None):
            with self.assertRaises(RuntimeError): delivery.pull('server','/bundle',self.dest)
        with self.assertRaises(ValueError): delivery.pull('-bad','/bundle',self.dest)
        with self.assertRaises(ValueError): delivery.pull('server','/bundle;cmd',self.dest)

if __name__=='__main__': unittest.main()
