"""Download the pinned model from Argos and verify it before extracting."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import requests
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://argos-net.com/v1/translate-en_es-1_0.argosmodel"
SHA256 = "d698d0ef87ad70d5d184b7fa6965905bf4368f09a2bb9ffb165a79bac96af0c4"
REQUIRED = ["model/model.bin", "model/shared_vocabulary.txt", "sentencepiece.model", "metadata.json", "README.md"]
MAX_DOWNLOAD = 150 * 1024 * 1024


def verify_archive(path):
    with Path(path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != SHA256:
        raise ValueError("El modelo descargado no coincide con la versión verificada. No se instaló.")


def extract_model(archive, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        # Never extract arbitrary archive paths or unused Stanza binaries.
        for name in REQUIRED:
            item = package.getinfo("en_es/" + name)
            if item.file_size > MAX_DOWNLOAD:
                raise ValueError("Archivo del modelo demasiado grande")
        for name in REQUIRED:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open("en_es/" + name) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def installed(models):
    try:
        receipt = json.loads((models / "en_es" / "INSTALLATION.json").read_text())
        return receipt.get("archive_sha256") == SHA256 and all((models / "en_es" / n).is_file() for n in REQUIRED)
    except (OSError, ValueError):
        return False


def install(models=None):
    models = Path(models or ROOT / "backend" / "models")
    if installed(models):
        print("Modelo local ya instalado.")
        return
    models.mkdir(parents=True, exist_ok=True)
    print("Descargando modelo inglés -> español (aproximadamente 84 MB)...", flush=True)
    with tempfile.TemporaryDirectory(prefix="model-", dir=models) as temp:
        temp = Path(temp)
        archive = temp / "model.zip"
        size = 0
        with requests.get(URL, stream=True, timeout=(15, 45)) as response, archive.open("wb") as output:
            response.raise_for_status()
            for chunk in response.iter_content(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError("La descarga supera el tamaño esperado")
                output.write(chunk)
        verify_archive(archive)
        staged = temp / "en_es"
        extract_model(archive, staged)
        receipt = {"source_url": URL, "archive_sha256": SHA256}
        (staged / "INSTALLATION.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        destination = models / "en_es"
        # Keep any pre-existing model as a recoverable backup during installation.
        previous = models / "en_es.previous"
        if destination.exists():
            if previous.exists():
                raise RuntimeError("Existe una copia en en_es.previous. Conservála o movela antes de reinstalar.")
            destination.rename(previous)
        try:
            staged.rename(destination)
        except Exception:
            if previous.exists() and not destination.exists():
                previous.rename(destination)
            raise
    print("Modelo verificado e instalado.")


if __name__ == "__main__":
    install()
