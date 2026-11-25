# lams.py: the title's text tables (/ui/lang/text_<language>.lang of ms3.psarc) and the text
# ids its menus use (lams="Group::Name", id="Group::Name" in the UI XML).
#   python scripts/lams.py <dir with extracted ui/> find <regex> [language]   ids whose text matches
#   python scripts/lams.py <dir with extracted ui/> get <Id::Name> [...]      the text of ids, every language found
# The directory is what `psarc.py <archive> extract "^/?ui/.*\.(xml|lang)$" <dir>` wrote (E:, never
# the repository: these are the title's own files). A .lang file is: u32 count, count x (u32 hash,
# u32 offset), then the texts (UTF-8, zero-terminated), big-endian; the hash of an id is found by
# trying the usual candidates on ids taken from the XML (printed on the first line).
import sys, os, re, struct, zlib, glob


def load(path):
    d = open(path, 'rb').read()
    n, = struct.unpack_from('>I', d, 0)
    base = 4 + 8 * n
    out = {}
    for i in range(n):
        h, off = struct.unpack_from('>II', d, 4 + 8 * i)
        end = d.index(b'\0', base + off)
        out[h] = d[base + off:end].decode('utf-8', 'replace')
    return out


def fnv1a(b):
    h = 2166136261
    for c in b:
        h = ((h ^ c) * 16777619) & 0xFFFFFFFF
    return h


def fnv1(b):
    h = 2166136261
    for c in b:
        h = ((h * 16777619) & 0xFFFFFFFF) ^ c
    return h


def djb2(b):
    h = 5381
    for c in b:
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


def sdbm(b):
    h = 0
    for c in b:
        h = (c + (h << 6) + (h << 16) - h) & 0xFFFFFFFF
    return h


HASHES = {'crc32': lambda b: zlib.crc32(b) & 0xFFFFFFFF, 'fnv1a': fnv1a, 'fnv1': fnv1, 'djb2': djb2, 'sdbm': sdbm}
FORMS = {'as is': lambda s: s, 'lower': str.lower, 'upper': str.upper}


def xml_ids(root):
    ids = set()
    for p in glob.glob(os.path.join(root, 'ui', '**', '*.xml'), recursive=True):
        t = open(p, 'rb').read().decode('latin-1')
        ids.update(re.findall(r'(?:lams|id)="([A-Za-z0-9_]+(?:::[^"$]+)+)"', t))
    return sorted(ids)


def find_hash(table, ids):
    best = (0, None, None)
    for hn, hf in HASHES.items():
        for fn, ff in FORMS.items():
            hits = sum(1 for i in ids if hf(ff(i).encode('utf-8')) in table)
            if hits > best[0]:
                best = (hits, hn, fn)
    return best


def main():
    root, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    langs = {os.path.basename(p)[5:-5]: load(p) for p in glob.glob(os.path.join(root, 'ui', 'lang', 'text_*.lang'))}
    ids = xml_ids(root)
    first = langs.get('english') or next(iter(langs.values()))
    hits, hn, fn = find_hash(first, ids)
    print('%d ids in the XML, %d found in the table with %s (%s)' % (len(ids), hits, hn, fn))
    if not hn:
        return
    key = lambda i: HASHES[hn](FORMS[fn](i).encode('utf-8'))
    if cmd == 'find':
        rx = re.compile(args[0], re.I)
        lang = langs[args[1]] if len(args) > 1 else first
        for i in ids:
            t = lang.get(key(i))
            if t is not None and rx.search(t):
                print('%-60s %s' % (i, t.replace('\n', ' / ')))
    elif cmd == 'get':
        for i in args:
            print(i)
            for name in sorted(langs):
                print('   %-10s %s' % (name, langs[name].get(key(i), '(absent)')))


main()
