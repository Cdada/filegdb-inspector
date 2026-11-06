"""Release boundary tests; no business files are used."""
import tempfile
import unittest
from pathlib import Path
from scripts.check_release import validate_name, validate_content, source_files


class ReleaseTests(unittest.TestCase):
    def test_reject_data_extensions_and_directories(self):
        for name in ('result.' + 'json', 'RESULT.' + 'JSON', 'scan.' + 'jsonl',
                     'sample.gdb/app.py', 'runtime/app.py', 'data/a.py',
                     'report.csv', '../app.py', '/app.py', 'private.zip', 'photo.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_name(name)

    def test_reject_personal_paths_and_binary(self):
        for raw in (('/' + 'Users/' + 'example/private').encode(), b'bad\x00binary'):
            with self.assertRaises(ValueError):
                validate_content('README.md', raw)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'RELEASE_FILES.txt').write_text('RELEASE_FILES.txt\napp.py\n')
            (root / 'app.py').symlink_to(root / 'RELEASE_FILES.txt')
            with self.assertRaises(ValueError):
                source_files(root)

    def test_real_release_is_source_only(self):
        files = source_files()
        self.assertIn('app.py', files)
        self.assertIn('LICENSE', files)
        self.assertNotIn('runtime', files)


if __name__ == '__main__':
    unittest.main()
