"""Synthetic onboarding and receiver checks; never edits real global memory."""
from pathlib import Path
import hashlib
import tempfile
import unittest
import path_memory
import reverse_receiver


class OnboardingTest(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'data'/'tmp';root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.root=Path(self.temp.name).resolve()
        self.memory=self.root/'AGENTS.md'
    def tearDown(self):self.temp.cleanup()

    def test_first_lookup_and_nonfixed_do_not_write(self):
        self.assertIsNone(path_memory.lookup(self.memory,'laptop'))
        with self.assertRaises(ValueError):path_memory.remember(self.memory,'laptop','D:/Files')
        self.assertFalse(self.memory.exists())

    def test_fixed_memory_preserves_other_preferences_and_clients(self):
        prefix='# Existing preferences\r\nDo not change.\r\n'
        self.memory.write_bytes(prefix.encode())
        path_memory.remember(self.memory,'laptop','D:/Files',True)
        path_memory.remember(self.memory,'desktop','/home/user/files',True)
        path_memory.remember(self.memory,'laptop','D:/NewFiles',True)
        self.assertTrue(self.memory.read_bytes().startswith(prefix.encode()))
        self.assertEqual(path_memory.lookup(self.memory,'laptop')['codex_temp_root'],'D:/NewFiles')
        self.assertEqual(path_memory.lookup(self.memory,'desktop')['codex_temp_root'],'/home/user/files')
        self.assertEqual(self.memory.read_text(encoding='utf-8').count(path_memory.START),1)
        self.assertIsNone(path_memory.lookup(self.memory,'third-computer'))

    def test_malformed_memory_is_not_overwritten(self):
        self.memory.write_text(path_memory.START,encoding='utf-8');before=self.memory.read_bytes()
        with self.assertRaises(ValueError):path_memory.remember(self.memory,'laptop','D:/Files',True)
        self.assertEqual(before,self.memory.read_bytes())
        with self.assertRaises(ValueError):path_memory.remember(self.root/'other','laptop','relative',True)

    def test_receiver_checks_hash_and_preserves_existing_file(self):
        data=b'<html>Final report</html>';sha=hashlib.sha256(data).hexdigest()
        with self.assertRaises(ValueError):reverse_receiver.accept_report(self.root,sha,b'bad')
        self.assertFalse((self.root/'report.html').exists())
        result=reverse_receiver.accept_report(self.root,sha,data)
        self.assertEqual(result['status'],'local-verified')
        self.assertEqual(reverse_receiver.accept_report(self.root,sha,data)['sha256'],sha)
        other=b'changed';other_sha=hashlib.sha256(other).hexdigest()
        with self.assertRaises(ValueError):reverse_receiver.accept_report(self.root,other_sha,other)
        self.assertEqual((self.root/'report.html').read_bytes(),data)

if __name__=='__main__':unittest.main()
