"""Seed the tail of WWS job modules that have code past their lifted code_end (1.06: MS_TITLE=BCES00484_106).

    python scripts/jobmods_seed_tail.py [--dry-run] [--only name_substr,...]

relift_jobmods.py follows direct branches, manual links and switch tables; code reached only through function
pointers stays interpreted (the 101 KB and 90 KB modules of 1.06: 677 -> 1341 functions once seeded). For each module
of the manifest this takes the first instruction after every `bi $0` (a return) located between the module's code_end
and its last non-zero byte as an extra function entry (the heuristic of scripts/lift_ms_plugins.py), then runs
relift_jobmods.py (fix-point, then --merge) for that module with $LBP_JOBMOD_EXTRA_FUNCS set. A wrong guess (a string
that looks like a return) only produces a function nobody calls. Afterwards: extend_jobmods.py, add_base0_at8000.py,
direct_bie.py, build.
"""
import json, os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
TITLE = os.environ.get('MS_TITLE', 'BCES00484')
SUF = '' if TITLE == 'BCES00484' else '_106'
MAN = os.path.join(ROOT, 'port', 'spu', 'jobmods_manifest%s.json' % SUF)
ELF = os.path.join(ROOT, 'game', TITLE, 'EBOOT.elf')
BASE = 0x4000

sys.path.insert(0, os.path.join(ROOT, '..', 'ps3recomp', 'tools'))
os.chdir(os.path.join(ROOT, '..', 'ps3recomp', 'tools'))
import lift_jobmods as L  # noqa: E402

dry = '--dry-run' in sys.argv
# modules with only 1-3 candidates are data past the code (strings that look like returns): seeding them would pull
# run-time-written data into the verified span and get the region rejected; --min n changes the threshold
MIN = int(sys.argv[sys.argv.index('--min') + 1]) if '--min' in sys.argv else 10
only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else []
raws = dict(L.find_engine_modules(open(ELF, 'rb').read()))
man = json.load(open(MAN))
py = sys.executable
todo = []
for m in man:
    if only and not any(o in m['name'] for o in only):
        continue
    raw = raws.get(m['ea'])
    if raw is None or m.get('base', BASE) != BASE:
        continue
    end = max((i for i in range(len(raw)) if raw[i]), default=-1) + 1
    words = [int.from_bytes(raw[i:i + 4], 'big') for i in range(0, end & ~3, 4)]
    seeds = set()
    for i, w in enumerate(words):
        if w != 0x35000000:
            continue
        j = i + 1
        while j < len(words) and words[j] in (0x00200000, 0x40200000):
            j += 1
        if j < len(words) and words[j] != 0 and BASE + 4 * j >= m['code_end'] and BASE + 4 * j < BASE + end:
            seeds.add(BASE + 4 * j)
    if len(seeds) >= MIN:
        todo.append((m['name'], sorted(seeds), m['code_end']))
print('%d module(s) with candidate entries past their code_end' % len(todo))
for name, seeds, ce in todo:
    print('  %s: code_end 0x%X, %d candidate(s)' % (name, ce, len(seeds)))
if dry:
    sys.exit(0)
for name, seeds, ce in todo:
    env = dict(os.environ, MS_TITLE=TITLE, LBP_JOBMOD_EXTRA_FUNCS=','.join(hex(s) for s in seeds))
    key = name.split('_')[1]
    for extra in ([], ['--merge']):
        r = subprocess.run([py, os.path.join(HERE, 'relift_jobmods.py')] + extra + ['--only', key], env=env,
                           capture_output=True, text=True, cwd=ROOT)
        tail = [l for l in r.stdout.splitlines() if 'code_end' in l or 'funcs=' in l][-2:]
        print('  %s %s -> %s' % (name, ' '.join(extra) or 'fixpoint', ' | '.join(t.strip() for t in tail)))
        if r.returncode:
            print(r.stderr[-400:])
