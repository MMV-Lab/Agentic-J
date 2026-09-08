"""
Runs ONE Groovy script in a throwaway Fiji JVM, then exits.

This exists so long batch scripts can be stopped for real. Groovy running in the
app's own JVM cannot be force-killed (JDK 21 removed Thread.stop, and an
uninterruptible plugin call — Coloc 2's Costes test being the standard example —
ignores every cooperative abort). A script running in its own process has no such
problem: SIGKILL always wins.

The trade-off is that this JVM does not share state with the app's Fiji, so it is
only used for scripts that source their own images from disk. `_should_run_in_subprocess`
in script_tools.py makes that call.

Run as:  python -m imagentj.groovy_worker <script_path> [purpose]

Deliberately reuses run_groovy_script() rather than reimplementing execution, so a
batch run is reported exactly like an in-process one (same window classification,
same SUMMARY/STATUS/ERRORS shape). The report is bracketed by markers because Fiji
floods stdout with plugin-discovery noise the parent must not mistake for output.
"""

import os
import sys

# Import as a package whether launched via -m or by path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The parent process supervises this run; a watchdog in here would be a second
# opinion with no way to report and would burn LLM calls.
os.environ["IMAGENTJ_WATCHDOG"] = "0"
# The dialog guard uses this to stop waiting immediately without dismissing the
# dialog first.  main() writes the structured failure report and os._exit() then
# kills the whole disposable JVM, so no post-dialog Groovy statement can run with
# silently accepted defaults.
os.environ["IMAGENTJ_BATCH_WORKER"] = "1"

REPORT_BEGIN = "===IMAGENTJ_GROOVY_REPORT_BEGIN==="
REPORT_END = "===IMAGENTJ_GROOVY_REPORT_END==="


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: groovy_worker.py <script_path> [purpose]\n")
        raise SystemExit(2)

    script_path = sys.argv[1]
    purpose = sys.argv[2] if len(sys.argv) > 2 else ""

    with open(script_path, encoding="utf-8") as handle:
        code = handle.read()

    from imagentj.imagej_context import get_ij
    from imagentj.tools.script_tools import run_groovy_script

    ij = get_ij()

    # live_sink echoes the script's output to real stdout as it is produced. The
    # parent's watchdog decides "stuck vs. working" from output silence, so
    # without this a healthy multi-hour batch would look dead and be killed.
    report = run_groovy_script(code, ij, purpose, live_sink=sys.stdout)

    sys.stdout.write(f"\n{REPORT_BEGIN}\n{report}\n{REPORT_END}\n")
    sys.stdout.flush()
    sys.stderr.flush()

    # Fiji's AWT/EDT threads are non-daemon, so a normal return would hang here
    # forever with the work already finished. The report is flushed; leave now.
    os._exit(0)


if __name__ == "__main__":
    main()
