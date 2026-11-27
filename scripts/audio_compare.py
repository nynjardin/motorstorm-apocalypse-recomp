"""Is the sound the port played the sound of the movie?

    python scripts/audio_compare.py <mix.f32> <ref.f32>

<mix.f32>: the port's final mix (AUDIO_WAV=<file>: raw float32 LE, stereo, 48 kHz, the whole run).
<ref.f32>: the movie's track decoded apart:
    ffmpeg -i movie.avi -vn -f f32le -ar 48000 -ac 2 ref.f32
Finds where the reference starts in the mix (first sound, then a lag search), and at several places of
the reference prints the best lag (a constant lag = no drift, no lost block), the correlation left/left,
right/right and left/right (a swap shows as a high cross value) and the level ratio mix / reference.
Pure Python (no numpy in the venv): windows of 4800 samples, lag search of +-1500 samples.
"""
import array, math, sys


def load(p):
    a = array.array('f')
    with open(p, 'rb') as f:
        data = f.read()
    a.frombytes(data[:len(data) // 8 * 8])
    return a[0::2], a[1::2]


def first_sound(ch, thr=1e-3):
    for i, v in enumerate(ch):
        if v > thr or v < -thr:
            return i
    return -1


def corr(a, ao, b, bo, n):
    sa = sb = sab = 0.0
    for i in range(n):
        x = a[ao + i]; y = b[bo + i]
        sa += x * x; sb += y * y; sab += x * y
    return (sab / math.sqrt(sa * sb) if sa > 0 and sb > 0 else 0.0), math.sqrt(sa / n), math.sqrt(sb / n)


def main():
    ml, mr = load(sys.argv[1]); rl, rr = load(sys.argv[2])
    m0 = first_sound(ml); r0 = first_sound(rl)
    print("mix: %.1f s, first sound at %.3f s; reference: %.1f s, first sound at %.3f s"
          % (len(ml) / 48000, m0 / 48000, len(rl) / 48000, r0 / 48000))
    base = m0 - r0                      # mix index of reference sample 0, first guess
    n = 4800
    for sec in (0.5, 2.0, 4.0, 6.0, 8.0, 9.5):
        ro = int(sec * 48000)
        if ro + n >= len(rl):
            break
        best = (-2.0, 0)
        for lag in range(-1500, 1501, 4):
            mo = base + ro + lag
            if mo < 0 or mo + n >= len(ml):
                continue
            c = corr(ml, mo, rl, ro, n)[0]
            if c > best[0]:
                best = (c, lag)
        for lag in range(best[1] - 4, best[1] + 5):
            mo = base + ro + lag
            if mo < 0 or mo + n >= len(ml):
                continue
            c = corr(ml, mo, rl, ro, n)[0]
            if c > best[0]:
                best = (c, lag)
        mo = base + ro + best[1]
        cll, rm, rrms = corr(ml, mo, rl, ro, n)
        crr = corr(mr, mo, rr, ro, n)[0]
        clr = corr(ml, mo, rr, ro, n)[0]
        print("ref %4.1f s: lag %+5d samples, corr L/L %.3f R/R %.3f L/R %.3f, level mix/ref %.3f"
              % (sec, best[1], cll, crr, clr, rm / rrms if rrms else 0))


if __name__ == '__main__':
    main()
