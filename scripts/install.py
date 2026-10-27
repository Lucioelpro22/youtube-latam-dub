"""Windows setup with a project-local virtual environment."""
from pathlib import Path
import platform
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 11) or sys.version_info >= (3, 15) or platform.architecture()[0] != "64bit":
        raise RuntimeError("Instalá Python de 64 bits, versión 3.11 a 3.14, desde python.org.")
    environment = ROOT / ".venv"
    executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not executable.exists():
        print("Creando entorno del proyecto...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(executable), "-m", "pip", "install", "-r", str(ROOT / "backend/requirements.txt")], check=True)
    subprocess.run([str(executable), str(ROOT / "scripts/download_model.py")], check=True)
    subprocess.run([str(executable), str(ROOT / "scripts/diagnose.py")], check=True)
    print("Instalación terminada. Abrí run_server.bat y cargá la carpeta extension en el navegador.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("No se completó la instalación:", exc, file=sys.stderr)
        sys.exit(1)
