from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .paths import is_frozen
from .steam_paths import find_steam_api_dll, find_steam_path

WORKER_SCRIPT = Path(__file__).resolve().parent / "idle_worker.py"
HEARTBEAT_MAX_AGE = 12.0


@dataclass
class IdleProcess:
    app_id: int
    process: subprocess.Popen
    work_dir: Path
    started_at: float = field(default_factory=time.time)

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    def heartbeat_ok(self) -> bool:
        hb = self.work_dir / "heartbeat.txt"
        if not hb.exists():
            return (time.time() - self.started_at) < 5.0
        try:
            age = time.time() - float(hb.read_text(encoding="ascii").strip())
            return age <= HEARTBEAT_MAX_AGE
        except Exception:
            return False


class IdleManager:
    """Spawn / stop per-app idle workers (one SteamAPI process each)."""

    def __init__(self, steam_path: str = "", dll_path: Path | None = None) -> None:
        config.ensure_dirs()
        self.steam_path = find_steam_path(steam_path)
        self.dll_path = dll_path or find_steam_api_dll(self.steam_path)
        self._procs: dict[int, IdleProcess] = {}
        self._failed: set[int] = set()

    def ensure_ready(self) -> None:
        if self.dll_path is None or not self.dll_path.exists():
            raise RuntimeError(
                "Не найден steam_api64.dll. Положи файл в папку native/ "
                "(обычно он уже есть в проекте)."
            )

    def start(self, app_id: int) -> IdleProcess:
        self.ensure_ready()
        existing = self._procs.get(app_id)
        if existing and existing.alive and existing.heartbeat_ok():
            return existing
        if existing:
            self.stop(app_id)

        work_dir = config.WORKERS_DIR / str(app_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        for name in ("worker_error.txt", "heartbeat.txt"):
            try:
                (work_dir / name).unlink(missing_ok=True)
            except OSError:
                pass

        local_dll = work_dir / "steam_api64.dll"
        if not local_dll.exists():
            local_dll.write_bytes(self.dll_path.read_bytes())  # type: ignore[union-attr]

        creationflags = 0
        startupinfo = None
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        # Prefer python.exe over pythonw for SteamAPI reliability (dev only)
        exe = sys.executable
        if not is_frozen() and sys.platform == "win32" and exe.lower().endswith(
            "pythonw.exe"
        ):
            candidate = Path(exe).with_name("python.exe")
            if candidate.exists():
                exe = str(candidate)

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["SteamAppId"] = str(app_id)
        env["SteamGameId"] = str(app_id)

        if is_frozen():
            cmd = [exe, "--idle-worker", str(app_id), "--dll", str(local_dll)]
        else:
            if not WORKER_SCRIPT.exists():
                raise RuntimeError(f"Не найден idle_worker.py: {WORKER_SCRIPT}")
            env["PYTHONPATH"] = str(config.ROOT) + os.pathsep + env.get(
                "PYTHONPATH", ""
            )
            cmd = [exe, str(WORKER_SCRIPT), str(app_id), "--dll", str(local_dll)]

        # Never PIPE stderr — Steam fills the pipe and workers hang
        proc = subprocess.Popen(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=startupinfo,
            env=env,
        )
        time.sleep(0.8)
        if proc.poll() is not None:
            err = ""
            err_file = work_dir / "worker_error.txt"
            if err_file.exists():
                err = err_file.read_text(encoding="utf-8", errors="replace").strip()
            self._failed.add(app_id)
            raise RuntimeError(
                f"Idle worker для {app_id} сразу завершился. "
                f"Steam запущен? {err}"
            )

        item = IdleProcess(app_id=app_id, process=proc, work_dir=work_dir)
        for _ in range(10):
            if item.heartbeat_ok() or not item.alive:
                break
            time.sleep(0.2)
        if not item.alive:
            self._failed.add(app_id)
            raise RuntimeError(f"Idle worker для {app_id} умер сразу после старта.")

        self._failed.discard(app_id)
        self._procs[app_id] = item
        return item

    def stop(self, app_id: int) -> None:
        item = self._procs.pop(app_id, None)
        if not item:
            return
        self._terminate(item)

    def stop_all(self) -> None:
        for app_id in list(self._procs):
            self.stop(app_id)

    def running_ids(self) -> list[int]:
        dead: list[int] = []
        for aid, p in self._procs.items():
            if not p.alive or not p.heartbeat_ok():
                dead.append(aid)
        for aid in dead:
            item = self._procs.pop(aid, None)
            if item:
                self._terminate(item)
        return list(self._procs)

    def healthy_count(self) -> int:
        return len(self.running_ids())

    def start_many(self, app_ids: list[int]) -> list[int]:
        started: list[int] = []
        for app_id in app_ids:
            self.start(app_id)
            started.append(app_id)
            time.sleep(0.75)
        return started

    @staticmethod
    def _terminate(item: IdleProcess) -> None:
        if item.process.poll() is not None:
            return
        try:
            item.process.terminate()
            try:
                item.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                item.process.kill()
        except Exception:
            try:
                item.process.kill()
            except Exception:
                pass
