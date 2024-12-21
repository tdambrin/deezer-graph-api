"""
Task model to automatically set task status and result
"""

import threading
from typing import Any, Callable

from status import StatusManager, ValidStatus


class Task:
    """
    To run tasks with targets, automatically sets task status and results.
    Threading mode optional.
    """

    def __init__(
        self,
        target: Callable,
        task_uuid: str,
        use_threading: bool = False,
        logger: Callable = print,
        **kwargs,
    ):
        self.target = target
        self.task_uuid = task_uuid
        self.use_threading = use_threading
        self.logger = logger
        self.kwargs = kwargs

    def run(self) -> Any:
        if not self.use_threading:
            return self._run()
        self._run_threading()

    def _run_threading(self):
        threading.Thread(target=self._set_task_context_and_run).start()

    def _run(self):
        self._set_task_context_and_run()

    def _set_task_context_and_run(self) -> Any:
        self.logger(f"Creating task {self.task_uuid}")
        StatusManager().create_task(task_id=self.task_uuid)
        self.logger(f"Running task {self.task_uuid}")
        StatusManager().run_task(task_id=self.task_uuid)
        try:
            task_result = self.target(**self.kwargs)
        except Exception as e:
            self.logger(f"Failed task {self.task_uuid}")
            StatusManager().fail_task(task_id=self.task_uuid, error=e)
            tb = e.__traceback__
            raise e.with_traceback(tb)

        self.logger(f"Completing task {self.task_uuid}")
        StatusManager().complete_task(
            self.task_uuid, status=ValidStatus.COMPLETED, result=task_result
        )
        return task_result
