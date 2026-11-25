"""Summarise a `samp_resolve.py --by-thread --top 3000` report by thread kind.

    python scripts/samp_summary.py <report.txt>

For each thread: name, share of samples that are waits (idle), and the busy time split into
lifted SPU code (by image/module), SPU interpreter, MFC, dispatch (drain/indirect/lookup), wake
machinery (coherency notify, channel wake, taskset wake), lock-line lock, other runtime.
Waits are the samples attributed (PS3_SAMPLE_CALLER=1) to spurs_pm_worker,
spurs_kernel_thread, spu_taskset_wait_signal, and the stale "ps3_thread_name" attribution.
"""
import collections, re, sys

IDLE = {"spurs_pm_worker", "spurs_kernel_thread", "spu_taskset_wait_signal", "ps3_thread_name",
        "<outside exe: waits / DLLs>"}
CAT = [("interp", ("spu_step", "spu_interp_run_until", "spu_smc_microstep")),
       ("mfc", ("mfc_", "spu_overlay_note_get", "gcm_note_spu_put")),
       ("dispatch", ("spu_drain_call", "spu_indirect_branch", "spu_lifted_lookup", "spu_irq_regs")),
       ("wake", ("spu_coh_notify_write", "spu_ch_wake", "spu_taskset_wake_written", "spurs_line_committed",
                 "spurs_commit_hook", "ppu_resv_break", "spu_coh_is_reserved", "spu_taskset_line_committed")),
       ("lockline", ("spu_lockline_",)),
       ("channels", ("spu_wrch", "spu_rdch", "spu_rchcnt"))]


def cat(sym):
    m = re.match(r"(jobmod_[0-9a-f]+|pm_wwsjob|ms_bank[AB]|spu_[0-9a-f]{12})_", sym)
    if m:
        return "lifted", m.group(1)
    for name, pre in CAT:
        if any(sym.startswith(x) for x in pre):
            return name, None
    return "other", sym


def main():
    threads, cur = [], None
    for l in open(sys.argv[1], encoding="utf-8-sig", errors="replace"):
        m = re.match(r"=== thread (\d+) \[(.*)\]", l)
        if m:
            cur = {"tid": m.group(1), "name": m.group(2), "rows": []}
            threads.append(cur)
            continue
        m = re.match(r"\s*[\d.]+%\s+(\d+)\s+(\S+)", l)
        if m and cur:
            cur["rows"].append((int(m.group(1)), m.group(2)))
    for t in threads:
        tot = sum(n for n, _ in t["rows"])
        idle = sum(n for n, s in t["rows"] if s in IDLE)
        busy = tot - idle
        if not tot:
            continue
        c, mods, other = collections.Counter(), collections.Counter(), collections.Counter()
        for n, s in t["rows"]:
            if s in IDLE:
                continue
            k, d = cat(s)
            c[k] += n
            if k == "lifted":
                mods[d] += n
            if k == "other":
                other[d] += n
        if busy * 100 < tot:      # idle thread
            print("%-7s %-14s busy %5.1f%%" % (t["tid"], t["name"], 100.0 * busy / tot))
            continue
        parts = " ".join("%s %.0f%%" % (k, 100.0 * v / busy) for k, v in c.most_common())
        print("%-7s %-14s busy %5.1f%% | %s" % (t["tid"], t["name"], 100.0 * busy / tot, parts))
        print("          lifted: " + ", ".join("%s %.0f%%" % (k, 100.0 * v / busy) for k, v in mods.most_common(4)))
        print("          other : " + ", ".join("%s %.0f%%" % (k, 100.0 * v / busy) for k, v in other.most_common(5)))


if __name__ == "__main__":
    main()
