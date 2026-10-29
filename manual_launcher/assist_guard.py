"""Deadline enforced at executor waits, captures and input checkpoints."""
from contextlib import contextmanager
import time


class AssistDeadlineReached(BaseException):
    # Upstream combat catches Exception to recover from failed rotations. A
    # deadline must escape that recovery loop and is caught by AssistedPlay.
    pass


@contextmanager
def executor_deadline(executor, deadline, clock=None):
    clock = clock or time.monotonic
    original_check = executor.check_enabled
    original_sleep = executor.sleep
    def check(*args, **kwargs):
        if clock() >= deadline:
            raise AssistDeadlineReached()
        return original_check(*args, **kwargs)
    def sleep(seconds):
        check(check_pause=False)
        original_sleep(min(seconds, max(0, deadline-clock())))
        check(check_pause=False)
    executor.check_enabled = check
    executor.sleep = sleep
    try:
        yield
    finally:
        executor.check_enabled = original_check
        executor.sleep = original_sleep


def release_inputs(interaction):
    if interaction is None:
        return
    for key in ('w','a','s','d','shift','alt','ctrl','e','q','r','f','space','1','2','3','4'):
        try:
            interaction.send_key_up(key)
        except Exception:
            pass
    for button in ('left','right','middle'):
        try:
            interaction.mouse_up(key=button)
        except Exception:
            pass
