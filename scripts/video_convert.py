"""Re-encode the title's movies to H.264, keeping everything else of each AVI.

    python scripts/video_convert.py <movie.avi | folder> <out folder> [--only _60] [--cq 24]
                                    [--encoder h264_nvenc] [--ffmpeg <ffmpeg.exe>] [--force]

The disc's ui/video/*.avi are XVID at 13-20 Mbit/s: 16 GB for three variants of 56 movies, of which
the port only reads the "_60" one (5.6 GB). This writes, for each input, an AVI of the SAME structure
whose video chunks hold H.264 access units instead (one per original frame, no B-frames, SPS/PPS in
band at each IDR, Annex B): the audio tracks (AC-3, up to 9 languages), the subtitle streams, the
chunk order and the JUNK padding are copied as they are, the headers get the new fourcc ('H264') and
buffer sizes, idx1 is rebuilt. The title's own player maps the 'H264' fourcc to cellVdec AVC.
The port plays <game folder>\\recomp\\video\\<name>.avi instead of the disc's file when it exists
(port/hle_overrides.cpp, PORT_VIDEO_CONVERTED=0 = never): give that folder as <out folder>.

Why not ffmpeg's own AVI muxer: it would drop the subtitle streams and renumber the audio tracks.
ffmpeg only decodes the picture and encodes the H.264 elementary stream (in a temporary file).
An input whose frame count does not match what the encoder returns is reported and skipped.
"""
import argparse, glob, os, struct, subprocess, sys, tempfile

FFMPEG_DEFAULT = r"E:\ms_perf\ffmpeg\ffmpeg-n8.1-latest-win64-lgpl-shared-8.1\bin\ffmpeg.exe"


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def chunks(data, start, end):
    """(fourcc, payload offset, size) of each chunk in data[start:end]."""
    o = start
    while o + 8 <= end:
        sz = u32(data, o + 4)
        yield data[o:o + 4], o + 8, sz
        o += 8 + sz + (sz & 1)


def split_annexb(es):
    """Access units of an Annex B stream that has an access unit delimiter (NAL 9) in front of each:
    list of (bytes, is_idr)."""
    starts = []
    i = 0
    n = len(es)
    while True:
        j = es.find(b"\x00\x00\x01", i)
        if j < 0 or j + 3 >= n:
            break
        starts.append(j)
        i = j + 3
    aus, cur, idr = [], None, False
    for k, j in enumerate(starts):
        t = es[j + 3] & 0x1F
        b = j - 1 if j > 0 and es[j - 1] == 0 else j     # 4-byte start code
        if t == 9:
            if cur is not None:
                aus.append((cur, b, idr))
            cur, idr = b, False
        elif t == 5:
            idr = True
    if cur is not None:
        aus.append((cur, n, idr))
    return [(es[a:b], k) for a, b, k in aus]


def convert(src, dst, a):
    d = open(src, "rb").read()
    if d[:4] != b"RIFF" or d[8:12] != b"AVI ":
        return "not a RIFF AVI"
    riff_end = 8 + u32(d, 4)
    if riff_end < len(d) - 0x10000 and d[riff_end:riff_end + 4] == b"RIFF":
        return "OpenDML (several RIFF chunks): not handled"
    hdrl = movi = idx1 = None
    for cc, o, sz in chunks(d, 12, min(riff_end, len(d))):
        if cc == b"LIST" and d[o:o + 4] == b"hdrl":
            hdrl = (o, sz)
        elif cc == b"LIST" and d[o:o + 4] == b"movi":
            movi = (o, sz)
        elif cc == b"idx1":
            idx1 = (o, sz)
    if not hdrl or not movi:
        return "no hdrl / movi"
    # the video stream: the first strl whose strh says 'vids'
    vid = None
    sn = 0
    patches = []          # (offset, bytes) into the head
    for cc, o, sz in chunks(d, hdrl[0] + 4, hdrl[0] + hdrl[1]):
        if cc == b"avih":
            avih = o
        if cc == b"LIST" and d[o:o + 4] == b"strl":
            strh = strf = None
            for c2, o2, s2 in chunks(d, o + 4, o + sz):
                if c2 == b"strh":
                    strh = o2
                elif c2 == b"strf":
                    strf = o2
            if strh is not None and d[strh:strh + 4] == b"vids" and vid is None:
                vid = (sn, strh, strf)
            sn += 1
    if vid is None:
        return "no video stream"
    vtag = (b"%02d" % vid[0])
    old_fourcc = d[vid[1] + 4:vid[1] + 8]
    if old_fourcc.upper() in (b"H264", b"AVC1", b"X264") and not a.force:
        return "already H.264"
    body = list(chunks(d, movi[0] + 4, movi[0] + movi[1]))
    if any(cc == b"LIST" for cc, _, _ in body):
        return "movi holds 'rec ' lists: not handled"
    vchunks = [k for k, (cc, _, sz) in enumerate(body) if cc[:2] == vtag and cc[2:] in (b"dc", b"db") and sz]
    # encode
    tmp = os.path.join(a.tmp or tempfile.gettempdir(), os.path.basename(dst) + ".h264")
    cmd = [a.ffmpeg, "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-an", "-sn",
           "-c:v", a.encoder, "-bf", "0", "-g", "30", "-fps_mode", "passthrough", "-pix_fmt", "yuv420p"]
    if a.encoder == "h264_nvenc":
        cmd += ["-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", str(a.cq), "-b:v", "0", "-maxrate", "16M",
                "-bufsize", "32M", "-profile:v", "high", "-level", "4.1", "-aud", "1", "-strict_gop", "1"]
    else:
        cmd += ["-b:v", "6M", "-bsf:v", "h264_metadata=aud=insert"]
    cmd += ["-f", "h264", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        return "ffmpeg failed: " + r.stderr.strip()[-300:]
    es = open(tmp, "rb").read()
    os.remove(tmp)
    aus = split_annexb(es)
    if len(aus) != len(vchunks):
        return "frame count: %d video chunks, %d access units encoded" % (len(vchunks), len(aus))
    # rebuild movi + idx1
    old_flags = {}
    if idx1:
        ents = [struct.unpack_from("<4sIII", d, idx1[0] + 16 * k) for k in range(idx1[1] // 16)]
        if len(ents) == len(body):
            old_flags = {k: e[1] for k, e in enumerate(ents)}
    out_body = bytearray(b"movi")
    index = bytearray()
    vmap = {k: n for n, k in enumerate(vchunks)}
    vmax = 0
    for k, (cc, o, sz) in enumerate(body):
        if k in vmap:
            payload, idr = aus[vmap[k]]
            flags = 0x10 if idr else 0
            vmax = max(vmax, len(payload))
        else:
            payload = d[o:o + sz]
            flags = old_flags.get(k, 0x10 if cc[2:] == b"wb" else 0)
        if cc not in (b"JUNK",):
            index += struct.pack("<4sIII", cc, flags, len(out_body), len(payload))
        out_body += cc + struct.pack("<I", len(payload)) + payload
        if len(payload) & 1:
            out_body += b"\x00"
    head = bytearray(d[12:movi[0] - 8])          # everything between 'AVI ' and the movi LIST header
    def put(abs_off, data):
        head[abs_off - 12:abs_off - 12 + len(data)] = data
    secs = max(1e-3, len(vchunks) * u32(d, avih) / 1e6)       # dwMicroSecPerFrame
    put(avih + 4, struct.pack("<I", int(len(out_body) / secs)))   # dwMaxBytesPerSec
    put(avih + 28, struct.pack("<I", vmax + 1024))                # dwSuggestedBufferSize
    put(vid[1] + 4, b"H264")                                     # strh fccHandler
    put(vid[1] + 36, struct.pack("<I", vmax + 1024))              # strh dwSuggestedBufferSize
    if vid[2] is not None:
        put(vid[2] + 16, b"H264")                                 # BITMAPINFOHEADER biCompression
        put(vid[2] + 20, struct.pack("<I", vmax))                 # biSizeImage
    tail = d[movi[0] + movi[1] + (movi[1] & 1):idx1[0] - 8] if idx1 else b""
    out = bytearray(b"RIFF\0\0\0\0AVI ") + head + b"LIST" + struct.pack("<I", len(out_body)) + out_body
    if len(out_body) & 1:
        out += b"\x00"
    out += tail + b"idx1" + struct.pack("<I", len(index)) + index
    struct.pack_into("<I", out, 4, len(out) - 8)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst + ".tmp", "wb") as f:
        f.write(out)
    os.replace(dst + ".tmp", dst)
    return "ok %d frames, %.1f -> %.1f MB (%.0f %%), video %s -> H264, largest unit %d KB" % (
        len(vchunks), len(d) / 1e6, len(out) / 1e6, 100.0 * len(out) / len(d), old_fourcc.decode("latin-1"), vmax // 1024)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--only", default="_60", help="only files whose name contains this (default _60; '' = all)")
    ap.add_argument("--cq", type=int, default=24, help="NVENC constant quality (lower = bigger, better)")
    ap.add_argument("--encoder", default="h264_nvenc")
    ap.add_argument("--ffmpeg", default=FFMPEG_DEFAULT)
    ap.add_argument("--tmp", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    files = [a.src] if os.path.isfile(a.src) else sorted(glob.glob(os.path.join(a.src, "*.avi")))
    files = [f for f in files if a.only in os.path.basename(f)]
    tin = tout = 0
    for f in files:
        dst = os.path.join(a.out, os.path.basename(f))
        if os.path.exists(dst) and not a.force:
            print("%-24s exists, kept" % os.path.basename(f))
            tout += os.path.getsize(dst); tin += os.path.getsize(f)
            continue
        res = convert(f, dst, a)
        print("%-24s %s" % (os.path.basename(f), res), flush=True)
        if res.startswith("ok"):
            tin += os.path.getsize(f); tout += os.path.getsize(dst)
    if tin:
        print("total %.2f GB -> %.2f GB" % (tin / 1e9, tout / 1e9))


if __name__ == "__main__":
    main()
