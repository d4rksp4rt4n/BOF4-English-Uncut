# Parse the PS1 BGM sequences (Sony SEP: "pQES", version 0, several songs) and report each song's
# loop markers (NRPN: CC99 = 20 loop start, CC99 = 30 loop end) in seconds, via the tempo map.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
import struct, sys, os

EMI_DIR = config.PS1_BGM
def emi_chunks(d):
    n = struct.unpack_from("<I", d)[0]
    ents = [struct.unpack_from("<4I", d, 16 + 16 * i) for i in range(n)]
    off, out = 0x800, []
    for size, _, kind, _ in ents:
        out.append((kind, d[off:off + size])); off = (off + size + 0x7FF) & ~0x7FF
    return out

def vlq(b, i):
    v = 0
    while True:
        c = b[i]; i += 1; v = (v << 7) | (c & 0x7F)
        if not c & 0x80: return v, i

def songs(sep):
    assert sep[:4] == b"pQES"
    i, out = 6, []
    while i + 13 <= len(sep):
        sid, res = struct.unpack_from(">HH", sep, i)
        tempo = int.from_bytes(sep[i + 4:i + 7], "big"); size = struct.unpack_from(">I", sep, i + 9)[0]
        if size == 0 or i + 13 + size > len(sep) + 4: break
        out.append((sid, res, tempo, sep[i + 13:i + 13 + size])); i += 13 + size
    return out

def loops(res, tempo, data):
    """(loop_start_s, loop_end_s, total_s) from the event stream; None where absent."""
    i, tick, status, nrpn = 0, 0, 0, {}
    tmap = [(0, tempo)]                         # (tick, us per quarter)
    marks = {}
    while i < len(data):
        dt, i = vlq(data, i); tick += dt
        b = data[i]
        if b & 0x80: status = b; i += 1
        if status == 0xFF:
            typ = data[i]; i += 1
            if typ == 0x2F: break
            if typ == 0x51: tmap.append((tick, int.from_bytes(data[i:i + 3], "big"))); i += 3
            else:                               # other meta: length byte (as in Sony SEQ)
                ln, i = vlq(data, i); i += ln
            continue
        hi = status & 0xF0
        if hi in (0xC0, 0xD0): i += 1; continue
        a, v = data[i], data[i + 1]; i += 2
        if hi == 0xB0 and a == 0x63:
            if v == 20: marks.setdefault("start", tick)
            elif v == 30: marks.setdefault("end", tick)
    def secs(t):
        s, prev_t, prev_tempo = 0.0, 0, tempo
        for mt, mtempo in tmap:
            if mt > t: break
            s += (mt - prev_t) * prev_tempo / res / 1e6; prev_t, prev_tempo = mt, mtempo
        return s + (t - prev_t) * prev_tempo / res / 1e6
    return (secs(marks["start"]) if "start" in marks else None,
            secs(marks["end"]) if "end" in marks else None, secs(tick))

def bgm_loops(n):
    d = open(os.path.join(EMI_DIR, f"BGM{n:03d}.EMI"), "rb").read()
    sep = next(c for k, c in emi_chunks(d) if k == 0x53455170)
    return [(sid, *loops(res, tempo, data)) for sid, res, tempo, data in songs(sep)]

if __name__ == "__main__":
    for n in map(int, sys.argv[1:]):
        for sid, ls, le, tot in bgm_loops(n):
            f = lambda x: "  -  " if x is None else f"{x:6.2f}"
            print(f"BGM{n:03d} song {sid}: loop start {f(ls)} s  loop end {f(le)} s  end {tot:6.2f} s")
