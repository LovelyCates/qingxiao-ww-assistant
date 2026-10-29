import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError,HTTPError
from release_tools.fetch_upstream_resources import fetch_one,resource_path

class ResourceFetch(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.source=Path(self.temp.name)
        self.data=b'upstream fixture';self.entry={'path':'assets/example.bin','bytes':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest()}
    def tearDown(self):self.temp.cleanup()
    def test_verified_download_is_written_atomically(self):
        with patch('release_tools.fetch_upstream_resources.request.urlopen',return_value=BytesIO(self.data)):
            self.assertEqual(fetch_one(self.entry,self.source,'https://example.invalid/'),'downloaded')
        self.assertEqual((self.source/self.entry['path']).read_bytes(),self.data)
        self.assertFalse(list(self.source.rglob('*.tmp')))
    def test_hash_failure_writes_nothing(self):
        with patch('release_tools.fetch_upstream_resources.request.urlopen',return_value=BytesIO(b'wrong data')):
            with self.assertRaisesRegex(ValueError,'checksum'):fetch_one(self.entry,self.source,'https://example.invalid/')
        self.assertFalse((self.source/self.entry['path']).exists())
    def test_verified_existing_file_never_downloads(self):
        path=self.source/self.entry['path'];path.parent.mkdir();path.write_bytes(self.data)
        with patch('release_tools.fetch_upstream_resources.request.urlopen') as download:
            self.assertEqual(fetch_one(self.entry,self.source,'https://example.invalid/'),'cached')
        download.assert_not_called()
    def test_modified_existing_file_is_preserved(self):
        path=self.source/self.entry['path'];path.parent.mkdir();path.write_bytes(b'user changes')
        with patch('release_tools.fetch_upstream_resources.request.urlopen') as download:
            with self.assertRaisesRegex(ValueError,'differs'):fetch_one(self.entry,self.source,'https://example.invalid/')
        download.assert_not_called();self.assertEqual(path.read_bytes(),b'user changes')
    def test_path_escape_and_unknown_resource_family_rejected(self):
        for name in ('../private.json','/assets/file','assets/../../private','src/code.py',r'assets\..\private'):
            with self.subTest(name=name),self.assertRaises(ValueError):resource_path({**self.entry,'path':name},self.source)
    def test_malformed_digest_or_size_rejected(self):
        for change in ({'sha256':'wrong'},{'bytes':True},{'bytes':100*1024*1024}):
            with self.subTest(change=change),self.assertRaises(ValueError):resource_path({**self.entry,**change},self.source)
    def test_transient_network_failure_retries_without_losing_verified_data(self):
        with patch('release_tools.fetch_upstream_resources.time.sleep'),patch('release_tools.fetch_upstream_resources.request.urlopen',side_effect=[URLError('temporary'),BytesIO(self.data)]) as get:
            self.assertEqual(fetch_one(self.entry,self.source,'https://example.invalid/'),'downloaded')
        self.assertEqual(get.call_count,2)
    def test_missing_upstream_file_is_not_retried(self):
        with patch('release_tools.fetch_upstream_resources.request.urlopen',side_effect=HTTPError('https://example.invalid/',404,'missing',{},None)) as get:
            with self.assertRaisesRegex(RuntimeError,'Failed to download'):fetch_one(self.entry,self.source,'https://example.invalid/')
        self.assertEqual(get.call_count,1)

if __name__=='__main__':unittest.main()
