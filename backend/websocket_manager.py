from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RunState:
    process: subprocess.Popen
    reader_thread: threading.Thread
    output_lines: List[str]
    started_at: float
    returncode: Optional[int]
    parsed_result: Optional[dict]
    build_in_docker: bool = False
    execution_result: Optional[dict] = None
    history_session_id: Optional[str] = None
    history_finalized: bool = False
    judge_verdict: Optional[dict] = None


class RunManager:
    def __init__(self) -> None:
        self.runs: Dict[str, RunState] = {}

    async def _read_stdout_async(self, run_state: RunState, max_capture_lines: int = 8000) -> None:
        loop = asyncio.get_event_loop()
        process = run_state.process

        while True:
            line = await loop.run_in_executor(None, process.stdout.readline)
            if line == "" and process.poll() is not None:
                break
            if line:
                run_state.output_lines.append(line.rstrip("\n"))
                if len(run_state.output_lines) > max_capture_lines:
                    del run_state.output_lines[:2000]

        if run_state.returncode is None:
            run_state.returncode = process.returncode if process.returncode is not None else process.poll()

    def _reader_worker(self, run_id: str) -> None:
        run_state = self.runs[run_id]
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._read_stdout_async(run_state))
        finally:
            run_state.returncode = run_state.process.returncode if run_state.process.returncode is not None else run_state.process.poll()
            loop.close()

    def start_run(self, run_id: str, cmd: List[str], cwd: str, env: Dict[str, str]) -> RunState:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        placeholder_thread = threading.Thread(target=lambda: None)
        run_state = RunState(
            process=process,
            reader_thread=placeholder_thread,
            output_lines=[],
            started_at=time.time(),
            returncode=None,
            parsed_result=None,
        )
        self.runs[run_id] = run_state

        reader_thread = threading.Thread(target=self._reader_worker, args=(run_id,), daemon=True)
        run_state.reader_thread = reader_thread
        reader_thread.start()
        return run_state

    def get_run(self, run_id: str) -> Optional[RunState]:
        return self.runs.get(run_id)

    def is_running(self, run_id: str) -> bool:
        run_state = self.get_run(run_id)
        return bool(run_state and run_state.process.poll() is None)

    def get_new_lines(self, run_id: str, from_index: int) -> List[str]:
        run_state = self.get_run(run_id)
        if not run_state:
            return []
        if from_index < 0:
            from_index = 0
        return run_state.output_lines[from_index:]
