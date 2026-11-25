#!/usr/bin/env python3
"""Write a short but valid copy of an AVI: original headers, the first N video frames with the
audio chunks interleaved before them, rebuilt movi/RIFF sizes, frame counts and idx1.
Used to make the title's movie player reach end of stream at once (see hle_overrides.cpp).
usage: short_avi.py <in.avi> <out.avi> [frames=10]"""
import struct, sys

src, dst = sys.argv[1], sys.argv[2]
keep = int(sys.argv[3]) if len(sys.argv) > 3 else 10
d = open(src, "rb").read()
assert d[:4] == b"RIFF" and d[8:12] == b"AVI "

def chunks(off, end):
    while off + 8 <= end:
        fid = d[off:off + 4]; sz = struct.unpack("<I", d[off + 4:off + 8])[0]
        yield off, fid, sz
        off += 8 + sz + (sz & 1)

hdr = None; movi = None
for off, fid, sz in chunks(12, len(d)):
    if fid == b"LIST" and d[off + 8:off + 12] == b"movi":
        movi = (off, sz)
    elif movi is None:
        pass
hdr_end = movi[0]
head = bytearray(d[12:hdr_end])            # hdrl + JUNK, patched below
body = bytearray(); index = bytearray(); nvid = 0; naud = 0; aud_bytes = 0
for off, fid, sz in chunks(movi[0] + 12, movi[0] + 8 + movi[1]):
    if fid.endswith(b"dc") or fid.endswith(b"db"):
        if nvid == keep: break
        nvid += 1
    elif fid.endswith(b"wb"):
        naud += 1
        aud_bytes += sz
    pos = 4 + len(body)                    # idx1 offsets are relative to 'movi'
    index += fid + struct.pack("<III", 0x10 if fid.endswith(b"dc") and nvid == 1 else 0, pos, sz)
    body += d[off:off + 8 + sz + (sz & 1)]

def patch(buf):
    # avih dwTotalFrames (+16 in data) ; strh dwLength (+32 in data), per stream type
    i = buf.find(b"avih")
    struct.pack_into("<I", buf, i + 8 + 16, nvid)
    j = 0
    while True:
        j = buf.find(b"strh", j)
        if j < 0: break
        typ = bytes(buf[j + 8:j + 12])
        if typ == b"vids":
            struct.pack_into("<I", buf, j + 8 + 32, nvid)
        elif typ == b"auds":
            # dwLength: chunk count for VBR audio (dwSampleSize 0), else bytes / dwSampleSize
            ssize = struct.unpack("<I", buf[j + 8 + 44:j + 8 + 48])[0]
            struct.pack_into("<I", buf, j + 8 + 32, aud_bytes // ssize if ssize else naud)
        j += 4
patch(head)
movi_list = b"LIST" + struct.pack("<I", 4 + len(body)) + b"movi" + body
idx1 = b"idx1" + struct.pack("<I", len(index)) + index
riff_body = b"AVI " + bytes(head) + movi_list + idx1
open(dst, "wb").write(b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body)
print(f"{dst}: {nvid} video + {naud} audio chunks, {8 + len(riff_body)} bytes")
