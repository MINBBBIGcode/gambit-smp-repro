# Gambit timed-mutex reproducibility probe

A bounded, independent investigation of the existing timed-mutex stress test associated with [Gambit issue760](https://github.com/gambit/gambit/issues/760). This repository contains an original test harness only. It does not contain a proposed Gambit fix, a bounty claim, or a finding of a new bug.

The source is pinned to `gambit/gambit@a6237f30ad94e33bb3a22e096aaed0dffc18814f`. The existing upstream `tests/unit-tests/06-thread/mutex_race_timeout.scm` is run unchanged. That test expects twenty independent counters of40,000 after timed locking by competing Scheme threads.

The manual workflow compares two fresh builds: unicore at one VM processor and SMP at two VM processors. Both use the same debug/O0 compiler settings, a successful bootstrap, bootclean, and a fresh build from current Scheme sources. Compiler/code-generation processes use the upstream GAMBOPT=p1 option, verified by a compiler smoke check. This isolates the build tool from the SMP runtime under test; runtime tests receive no build environment override and explicitly verify one or two VM processors. Each process has a finite deadline. A crash, timeout, assertion failure and infrastructure failure are recorded separately. Three fresh-process samples per mode are a limited observation, not proof of absence or root cause.

The [initial run](https://github.com/MINBBBIGcode/gambit-smp-repro/actions/runs/35401158284) passed all three unicore samples but failed compiling regenerated SMP compiler C before any SMP test. The revised build is a controlled diagnostic comparison, not a claimed fix for that compiler failure. Logs retain both the first error context and the final diagnostic tail.

Only standard Ubuntu public-repository runners are used. There are no secrets, dependency caches, uploaded Actions artifacts, deployments, service accounts, or payment operations. Results are emitted in ordinary workflow logs, which can be retrieved after the run. Jobs have a35-minute ceiling and cannot run on private repositories or other owners' forks through this workflow. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Run the manual **Timed mutex comparison** workflow. It has no user-controlled input and executes the pinned source. A green workflow means the observational probe completed; read each sample and FINAL_RESULT to determine whether the upstream test passed. The harness deliberately requires the expected GitHub Actions environment; it is not an installer for a developer machine.

Generated build directories and logs are ephemeral. The original Gambit code and tests retain their upstream licenses and are fetched directly from their source, not republished here. The harness is AI-assisted. No human code review, maintainer acceptance, payment, or successful runtime result is claimed until separately verified.
