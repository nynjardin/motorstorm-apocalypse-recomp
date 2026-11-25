# Dynamic instruction mix of the lifted PPU code, estimated from a host profile.
#
#   python scripts/prof_mix.py <resolved.txt> [--recomp work/BCES00484/recomp] [--top 25]
#
# <resolved.txt> is the output of scripts/samp_resolve.py (percent, samples, symbol per line).
# Each sampled lifted function (func_XXXXXXXX) contributes its sample count split by the share
# of each statement category in its lifted source (scalar FP, VMX float, VMX other, guest loads,
# guest stores, compares, calls, the rest): a rough but cheap answer to "what kind of code does
# the thread spend its time in?" (2026-11-23: is PPU_FAST_FP / a VMX fast path worth a rebuild?).
# It assumes time is spread evenly over a function's statements, which is false in detail and
# fair on average over thousands of functions.
import argparse, glob, io, os, re, sys
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument('resolved')
ap.add_argument('--recomp', default=os.path.join(os.path.dirname(__file__), '..', 'work', 'BCES00484', 'recomp'))
ap.add_argument('--top', type=int, default=25)
a = ap.parse_args()

samples = Counter(); total = 0; other = Counter()
for line in io.open(a.resolved, encoding='latin-1'):
    m = re.match(r'\s*[\d.]+%\s+(\d+)\s+(\S+)', line)
    if not m: continue
    n = int(m.group(1)); sym = m.group(2); total += n
    f = re.search(r'func_([0-9A-Fa-f]{8})', sym)
    if f: samples[f.group(1).upper()] += n
    else: other[sym] += n

CATS = [
    ('fp scalar',  re.compile(r'ppu_f(add|sub|mul|div|madd|p_single|rsp)|ctx->fpr\[\d+\] = [^v]')),
    ('vmx float',  re.compile(r'vmx_v(maddfp|nmsubfp|addfp|subfp|cmp..fp|rsqrtefp|refp|cf[su]x|ct[su]xs|maxfp|minfp|rfi.)')),
    ('vmx other',  re.compile(r'ctx->vr\[|vmx_v')),
    ('fp load/store', re.compile(r'float ftmp|ctx->fpr\[')),
    ('call',       re.compile(r'DRAIN_TRAMPOLINE|ps3_indirect_call|func_[0-9A-F]{8}\(ctx\)')),
    ('store',      re.compile(r'vm_write(8|16|32|64)\(')),
    ('load',       re.compile(r'vm_read(8|16|32|64)\(')),
    ('compare',    re.compile(r'cr_val|ctx->cr = ')),
    ('branch',     re.compile(r'\bgoto\b|return;')),
]
mix = Counter(); found = 0; fsamples = 0
want = set(samples)
hdr = re.compile(r'^(?:static )?void (?:\w+_)?func_([0-9A-F]{8})\(ppu_context\* ctx\)')
per_func = {}
for path in sorted(glob.glob(os.path.join(a.recomp, 'ppu_recomp_*.cpp'))):
    cur = None; cnt = None
    for line in io.open(path, encoding='latin-1'):
        if cur is None:
            m = hdr.match(line)
            if m and m.group(1) in want: cur = m.group(1); cnt = Counter()
            continue
        if line.startswith('}'):
            per_func[cur] = cnt; cur = None; continue
        s = line.strip()
        if not s or s.startswith('loc_') or s.startswith('/*') or s == 'PPU_MM_SNAP': continue
        for name, rx in CATS:
            if rx.search(s): cnt[name] += 1; break
        else: cnt['other int'] += 1
for f, cnt in per_func.items():
    n = sum(cnt.values())
    if not n: continue
    found += 1; fsamples += samples[f]
    for k, v in cnt.items(): mix[k] += samples[f] * v / n

print('samples: %d total, %d in %d lifted functions (%d found in the sources), %d elsewhere'
      % (total, sum(samples.values()), len(samples), found, sum(other.values())))
print('estimated mix of the lifted-code samples:')
for k, v in mix.most_common():
    print('  %-14s %5.1f %%' % (k, 100.0 * v / max(fsamples, 1)))
print('top non-lifted symbols:')
for k, v in other.most_common(a.top):
    print('  %5.1f %%  %s' % (100.0 * v / total, k))
