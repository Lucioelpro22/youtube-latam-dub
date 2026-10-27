import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import download_model
import build_release
from fastapi.testclient import TestClient
from server import app


class InstallerTests(unittest.TestCase):
    def test_invalid_model_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bad.zip"
            archive.write_bytes(b"not the expected model")
            with self.assertRaises(ValueError): download_model.verify_archive(archive)

    def test_only_required_model_paths_are_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fake.zip"
            with zipfile.ZipFile(archive, "w") as package:
                for name in download_model.REQUIRED:
                    package.writestr("en_es/" + name, "test data")
                package.writestr("../../escape.txt", "bad")
                package.writestr("en_es/stanza/unneeded.pt", "unneeded")
            output = Path(directory) / "installed"
            download_model.extract_model(archive, output)
            self.assertEqual(sorted(p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()), sorted(download_model.REQUIRED))

    def test_release_excludes_models_personal_paths_and_backups(self):
        paths = [p.relative_to(build_release.ROOT).as_posix() for p in build_release.public_files()]
        self.assertIn("scripts/download_model.py", paths)
        self.assertIn("extension/icon.png", paths)
        for name in paths:
            self.assertFalse(any(part in name.split("/") for part in ["backups", "models", ".venv", "__pycache__"]))
            self.assertFalse(name.endswith((".mp3", ".mp4", ".log")))


class PublicApiTests(unittest.TestCase):
    def setUp(self): self.client = TestClient(app)

    def test_rejects_invalid_voice_without_contacting_provider(self):
        result = self.client.post("/api/dub", json={"text": "hello", "voice": "unlisted"})
        self.assertEqual(result.status_code, 422)

    def test_rejects_invalid_speech_rate(self):
        for rate in ["fast", "+999%", "-99%"]:
            result = self.client.post("/api/dub", json={"text": "hello", "rate": rate})
            self.assertEqual(result.status_code, 422)

    def test_youtube_origin_allowed(self):
        response = self.client.options("/api/dub", headers={"Origin": "https://www.youtube.com", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "https://www.youtube.com")

    def test_unrelated_origin_not_allowed(self):
        response = self.client.options("/api/dub", headers={"Origin": "https://unrelated.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__": unittest.main()
