"""Artificial CPU load: <n> busy processes for <seconds> (default 8 for 600 s).

    python scripts/cpu_load.py [n] [seconds]

The intermittent freezes of the port showed up mostly on a loaded machine (2026-11-21 evening,
~40 % of the CPU taken by other programs). This reproduces that condition for
scripts/catch_freeze.ps1 runs. Stop it early by creating the file %TEMP%\cpu_load.stop: every
worker checks it a few times a second (killing the parent alone leaves the workers running:
that happened on 2026-11-22 and saturated the user's machine).
"""
import multiprocessing as mp, os, sys, time

STOP = os.path.join(os.environ.get("TEMP", "."), "cpu_load.stop")


def burn(until):
    x = 0
    while time.time() < until and not os.path.exists(STOP):
        for _ in range(200000):
            x = (x * 1103515245 + 12345) & 0xFFFFFFFF


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 600
    until = time.time() + secs
    if os.path.exists(STOP):
        os.remove(STOP)
    ps = [mp.Process(target=burn, args=(until,), daemon=True) for _ in range(n)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
