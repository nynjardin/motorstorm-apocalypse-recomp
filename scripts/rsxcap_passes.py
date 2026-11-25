"""Summarise an RSX_CAP manifest into passes (runs of ops on the same target)."""
import re
import sys

path = sys.argv[1]
ops = []
cur = None
for line in open(path, encoding='latin-1'):
    m = re.match(r'op(\d+) (DRAW|CLEAR|COPY)\s+(.*)', line)
    if m:
        cur = {'op': int(m.group(1)), 'kind': m.group(2), 'rest': m.group(3), 'tex': []}
        ops.append(cur)
        continue
    m = re.match(r'\s+t(\d+) off=0x([0-9A-F]+) fmt=0x([0-9A-F]+) \S+ (\d+x\d+)', line)
    if m and cur is not None:
        cur['tex'].append('t%s:%s(%s)' % (m.group(1), m.group(2)[1:], m.group(4)))


def field(rest, name):
    m = re.search(name + r'=(\S+)', rest)
    return m.group(1) if m else '?'


runs = []
for o in ops:
    key = (o['kind'] == 'COPY', field(o['rest'], 'rt'), field(o['rest'], 'mrt'),
           field(o['rest'], 'vp'), field(o['rest'], 'cmask'))
    if runs and runs[-1]['key'] == key and o['kind'] != 'COPY':
        runs[-1]['n'] += 1
        runs[-1]['last'] = o['op']
        runs[-1]['fps'].add(field(o['rest'], 'fp'))
        runs[-1]['clears'] += o['kind'] == 'CLEAR'
        runs[-1]['verts'] += int(field(o['rest'], 'n')) if o['kind'] == 'DRAW' else 0
    else:
        runs.append({'key': key, 'first': o['op'], 'last': o['op'], 'n': 1,
                     'fps': {field(o['rest'], 'fp')}, 'clears': int(o['kind'] == 'CLEAR'),
                     'verts': int(field(o['rest'], 'n')) if o['kind'] == 'DRAW' else 0,
                     'tex': ' '.join(o['tex'][:6]), 'rest': o['rest'][:90] if o['kind'] == 'COPY' else ''})
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 0
for r in runs:
    if r['last'] < lo:
        continue
    copy, rt, mrt, vp, cm = r['key']
    print('op%04d-%04d n=%4d clr=%d v=%7d rt=%s mrt=%s vp=%s cmask=%s fps=%d %s %s' % (
        r['first'], r['last'], r['n'], r['clears'], r['verts'], rt, mrt, vp, cm, len(r['fps']),
        r['tex'] if r['n'] < 4 else '', r['rest']))
