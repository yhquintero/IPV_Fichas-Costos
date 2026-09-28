"""Pruebas de la réplica de backups fuera del equipo (carpetas espejo y S3 SigV4)."""
import hashlib
import os
import tempfile
import threading
import unittest
from typing import ClassVar
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import offsite
import server


class SigV4Test(unittest.TestCase):
    def test_official_aws_s3_example(self):
        """Ejemplo «GET Object» de la documentación de AWS (Signature Version 4)."""
        headers = offsite.sign_v4(
            "GET", "https://examplebucket.s3.amazonaws.com/test.txt", {"range": "bytes=0-9"},
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "us-east-1",
            "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            datetime(2013, 5, 24, tzinfo=timezone.utc))
        self.assertEqual(
            headers["authorization"],
            "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
            "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


class MirrorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _backup(self, name, content=b"copia"):
        p = self.root / name
        p.write_bytes(content)
        return p

    def test_copy_verify_and_retention(self):
        mirror = self.root / "usb"
        with mock.patch.object(offsite, "MIRROR_DIRS", [str(mirror)]), mock.patch.object(offsite, "MIRROR_KEEP", 2):
            for i in range(4):
                src = self._backup(f"ipv_backup_2026092{i}_000000.db", f"datos {i}".encode())
                res = offsite.replicate(src, encrypted=True)
                self.assertTrue(res["results"][0]["ok"], res)
            (mirror / "ipv_export_20260101_000000.db").write_bytes(b"otra serie")  # no la toca
            offsite.replicate(src, encrypted=True)
        kept = sorted(p.name for p in mirror.glob("ipv_backup_*.db"))
        self.assertEqual(kept, ["ipv_backup_20260922_000000.db", "ipv_backup_20260923_000000.db"])
        self.assertTrue((mirror / "ipv_export_20260101_000000.db").exists())
        line = (mirror / "ipv_backup_20260923_000000.db.sha256").read_text().split()
        self.assertEqual(line[0], hashlib.sha256(b"datos 3").hexdigest())
        self.assertFalse(list(mirror.glob("*.partial")))

    def test_unreachable_mirror_reports_error_without_raising(self):
        blocker = self._backup("no-es-carpeta")
        src = self._backup("ipv_backup_20260901_000000.db")
        with mock.patch.object(offsite, "MIRROR_DIRS", [str(blocker / "sub")]):
            res = offsite.replicate(src, encrypted=True)
        self.assertFalse(res["results"][0]["ok"])
        self.assertEqual(offsite.status()["last"]["file"], src.name)

    def test_s3_requires_https(self):
        src = self._backup("ipv_backup_20260901_000000.db")
        with mock.patch.multiple(offsite, S3_ENDPOINT="http://inseguro:9000", S3_BUCKET="b",
                                 S3_ACCESS_KEY="a", S3_SECRET_KEY="s"), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IPV_BACKUP_S3_ALLOW_HTTP", None)
            res = offsite.replicate(src, encrypted=True)
        self.assertFalse(res["results"][0]["ok"])
        self.assertIn("HTTPS", res["results"][0]["error"])


class FakeS3(BaseHTTPRequestHandler):
    """S3 mínimo: comprueba la firma recalculándola con el secreto y el SHA-256 del cuerpo."""
    store: ClassVar[dict] = {}
    secret = "secreto-de-prueba"

    def do_PUT(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        sha = hashlib.sha256(body).hexdigest()
        amz_date = datetime.strptime(self.headers["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        url = f"http://{self.headers['Host']}{self.path}"
        expected = offsite.sign_v4("PUT", url, {"content-type": self.headers["Content-Type"],
                                                "x-amz-meta-sha256": self.headers["x-amz-meta-sha256"]},
                                   sha, "us-east-1", "AK", self.secret, amz_date)
        ok = (expected["authorization"] == self.headers["Authorization"]
              and sha == self.headers["x-amz-content-sha256"])
        if ok:
            FakeS3.store[self.path] = body
        self.send_response(200 if ok else 403)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class S3UploadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeS3)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_signed_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ipv_backup_20260928_010000.db"
            src.write_bytes(os.urandom(4096))
            conf = dict(S3_ENDPOINT=f"http://127.0.0.1:{self.httpd.server_port}", S3_BUCKET="copias",
                        S3_ACCESS_KEY="AK", S3_SECRET_KEY=FakeS3.secret, S3_PREFIX="ipv/")
            with mock.patch.multiple(offsite, **conf), mock.patch.dict(os.environ, {"IPV_BACKUP_S3_ALLOW_HTTP": "1"}):
                ok = offsite.replicate(src, encrypted=True)["results"][0]
                with mock.patch.object(offsite, "S3_SECRET_KEY", "otra"):
                    bad = offsite.replicate(src, encrypted=True)["results"][0]
            self.assertTrue(ok["ok"], ok)
            self.assertEqual(FakeS3.store["/copias/ipv/ipv_backup_20260928_010000.db"], src.read_bytes())
            self.assertFalse(bad["ok"])
            self.assertIn("403", bad["error"])


class AutoBackupIntegrationTest(unittest.TestCase):
    def test_scheduled_backup_is_replicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            mirror = Path(tmp) / "nas"
            old_db = server.DB_PATH
            server.DB_PATH = Path(tmp) / "ipv.db"
            try:
                server.init_db()
                with mock.patch.object(offsite, "MIRROR_DIRS", [str(mirror)]), \
                        mock.patch.object(server, "ROOT", Path(tmp)):
                    info = server.auto_backup()
            finally:
                server.DB_PATH = old_db
            self.assertTrue(info["offsite"][0]["ok"])
            self.assertTrue((mirror / info["filename"]).exists())


if __name__ == "__main__":
    unittest.main()
