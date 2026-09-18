"""Bounded public CI reproducibility probe; no installation or external writes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

SOURCE = "https://github.com/gambit/gambit.git"
COMMIT = "a6237f30ad94e33bb3a22e096aaed0dffc18814f"
TEST = "tests/unit-tests/06-thread/mutex_race_timeout.scm"
EXPECTED_REPOSITORY = "MINBBBIGcode/gambit-smp-repro"


def bounded(command, *, cwd, seconds, label):
    """Kill the process group at timeout and retain a bounded diagnostic tail."""
    started = time.monotonic()
    log = Path(cwd) / (label + ".log")
    with log.open("wb") as stream:
        child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=stream, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        timed_out = False
        try:
            child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
    with log.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - 6000))
        tail = stream.read().decode("utf-8", errors="replace")
    result = dict(label=label, command=command, returncode=child.returncode,
                  timed_out=timed_out, elapsed_seconds=round(time.monotonic()-started, 3),
                  output_bytes=size, tail=tail)
    print("STEP_RESULT " + json.dumps(result), flush=True)
    return result


def require_step(command, *, cwd, seconds, label):
    result = bounded(command, cwd=cwd, seconds=seconds, label=label)
    if result["timed_out"] or result["returncode"] != 0:
        raise RuntimeError(label + ": infrastructure/build failed")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("unicore", "smp"))
    args = parser.parse_args()
    if (platform.system() != "Linux" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY):
        raise SystemExit("This probe is restricted to the reviewed public CI job.")
    workspace = Path.cwd().resolve()
    source = workspace / "gambit"
    if source.exists():
        raise SystemExit("Refusing a reused source/build directory.")
    source.mkdir()
    record = dict(mode=args.mode, source=SOURCE, source_commit=COMMIT,
                  harness_commit=os.environ.get("GITHUB_SHA"),
                  runtime_reproduction="NOT_RUN", repetitions=[], source_patched=False)
    try:
        require_step(["git", "init", "."], cwd=source, seconds=30, label="init")
        require_step(["git", "remote", "add", "origin", SOURCE], cwd=source,
                     seconds=30, label="remote")
        require_step(["git", "fetch", "--depth=1", "origin", COMMIT], cwd=source,
                     seconds=90, label="fetch")
        require_step(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=source,
                     seconds=30, label="checkout")
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                         text=True, timeout=10).strip()
        if actual != COMMIT:
            raise RuntimeError("Source revision mismatch")
        record["test_sha256"] = hashlib.sha256((source / TEST).read_bytes()).hexdigest()
        record["compiler"] = subprocess.check_output(["gcc", "--version"], text=True,
                                                     timeout=10).splitlines()[0]
        flags = ["./configure", "--enable-c-opt=-O0", "--enable-c-opt-rts=-O0",
                 "--enable-debug", "--enable-debug-c-backtrace"]
        flags += (["--enable-smp", "--enable-multiple-threaded-vms"]
                  if args.mode == "smp" else
                  ["--disable-smp", "--disable-multiple-threaded-vms"])
        record["configure_flags"] = flags[1:]
        require_step(flags, cwd=source, seconds=120, label="configure")
        # Current .scm must be compiled; stale release .c files are insufficient.
        require_step(["make", "-j2", "bootstrap"], cwd=source, seconds=600, label="bootstrap")
        require_step(["make", "bootclean"], cwd=source, seconds=60, label="bootclean")
        require_step(["make", "-j2", "core"], cwd=source, seconds=600, label="core")
        processors = 2 if args.mode == "smp" else 1
        runtime = (f"-:p{processors},~~lib={source}/lib,~~bin={source}/bin,"
                   f"~~include={source}/include")
        gsi = str(source / "gsi/gsi")
        smoke = require_step([gsi, runtime, "-f", "-e",
                              "(write (##current-vm-processor-count)) (newline)"],
                             cwd=source, seconds=20, label="processor-smoke")
        if smoke["tail"].strip() != str(processors):
            raise RuntimeError("Actual VM processor count differs from requested mode")
        record["vm_processors"] = processors
        expression = ('(load "' + TEST + '") '
                      '(if ##failed-test? '
                      '(begin (display "TEST_ASSERTION_FAILED") (newline) (exit 1)) '
                      '(begin (display "COUNTERS ") (write result) (newline) '
                      '(display "TEST_PASS") (newline) (exit 0)))')
        expected_counters = "COUNTERS (" + " ".join(["40000"] * 20) + ")"
        for index in range(1, 4):
            result = bounded([gsi, runtime, "-f", "-e", expression],
                             cwd=source, seconds=90, label=f"sample-{index}")
            if result["timed_out"]:
                outcome = "TIMEOUT"
            elif result["returncode"] < 0:
                outcome = "PROCESS_SIGNAL"
            elif result["returncode"] == 1 and "TEST_ASSERTION_FAILED" in result["tail"]:
                outcome = "ASSERTION_FAILURE"
            elif result["returncode"] != 0:
                outcome = "NONZERO_EXIT"
            elif expected_counters not in result["tail"] or "TEST_PASS" not in result["tail"]:
                outcome = "MISSING_OR_INCORRECT_RESULT"
            else:
                outcome = "PASS"
            record["repetitions"].append(dict(index=index, outcome=outcome, **result))
        record["runtime_reproduction"] = (
            "NO_FAILURE_OBSERVED_IN_LIMITED_SAMPLES"
            if all(x["outcome"] == "PASS" for x in record["repetitions"])
            else "FAILURE_OBSERVED_NEEDS_MINIMIZATION")
        record["interpretation"] = "No bug, fix, novelty, award, or payment inferred from this probe alone."
    except Exception as error:
        record["infrastructure_error"] = str(error)
        record["runtime_reproduction"] = "INCOMPLETE_INFRASTRUCTURE_FAILURE"
    print("FINAL_RESULT " + json.dumps(record), flush=True)
    if record["runtime_reproduction"] == "INCOMPLETE_INFRASTRUCTURE_FAILURE":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
