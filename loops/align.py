# Align a PC music recording with its PS1 sequence: PC_time = offset + ratio * PS1_time.
# PS1 side: note-on times (velocity-weighted) from the SEQ, played through the loop twice.
# PC side: spectral-flux onset envelope. Search ratio, find offset by cross-correlation.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config, os
import struct, sys, numpy as np
import sep
from selfsim import decode

RATE = 100                                            # envelope frames per second

def notes(res, tempo, data):
    """[(seconds, velocity)] for one pass; tempo changes honoured."""
    i, tick, status, out, tmap = 0, 0, 0, [], [(0, tempo)]
    def secs(t):
        s, pt, pv = 0.0, 0, tempo
        for mt, mv in tmap:
            if mt > t: break
            s += (mt - pt) * pv / res / 1e6; pt, pv = mt, mv
        return s + (t - pt) * pv / res / 1e6
    while i < len(data):
        dt, i = sep.vlq(data, i); tick += dt; b = data[i]
        if b & 0x80: status = b; i += 1
        if status == 0xFF:
            typ = data[i]; i += 1
            if typ == 0x2F: break
            if typ == 0x51: tmap.append((tick, int.from_bytes(data[i:i + 3], "big"))); i += 3
            else: ln, i = sep.vlq(data, i); i += ln
            continue
        hi = status & 0xF0
        if hi in (0xC0, 0xD0): i += 1; continue
        a, v = data[i], data[i + 1]; i += 2
        if hi == 0x90 and v > 0: out.append((secs(tick), v))
    return out

def ps1_env(res, tempo, data, passes=3):
    ls, le, tot = sep.loops(res, tempo, data)
    ns = notes(res, tempo, data)
    ev = list(ns)
    if ls is not None and le is not None:
        body = [(t - ls, v) for t, v in ns if ls <= t < le]
        for k in range(1, passes):
            ev += [(le + (k - 1) * (le - ls) + t, v) for t, v in body]
    n = int((max(t for t, _ in ev) + 2) * RATE)
    e = np.zeros(n)
    for t, v in ev: e[int(t * RATE)] += v
    return e, ls, le

def pc_env(x):
    hop = 44100 // RATE; n = len(x) // hop
    sp = np.log1p(np.abs(np.fft.rfft(x[:n * hop].reshape(n, hop) * np.hanning(hop), axis=1)))
    return np.concatenate([[0], np.maximum(0, np.diff(sp, axis=0)).sum(1)])

def smooth(e, w=3):
    k = np.hanning(2 * w + 1); return np.convolve(e, k / k.sum(), "same")

def align(pc, ps):
    """best (ratio, offset_s, score): pc(t) ~ ps((t - offset) / ratio)."""
    a = smooth(pc - pc.mean())
    best = (1.0, 0.0, -1e9)
    for ratio in np.arange(0.80, 1.25, 0.0025):
        idx = (np.arange(int(len(ps) * ratio)) / ratio).astype(int)
        b = smooth(ps[idx]); b = b - b.mean()
        n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
        c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
        lags = np.r_[0:int(5 * RATE), n - int(5 * RATE):n]            # offset within +-5 s
        k = lags[np.argmax(c[lags])]
        sc = c[k] / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
        if sc > best[2]: best = (ratio, (k if k < n // 2 else k - n) / RATE, sc)
    return best

def pc_parts(n):
    d = open(os.path.join(config.CLEAN_DAT, f"BGM{n:03d}.DAT"), "rb").read()
    base, i, out = 0x10, 0x10, {}
    while d[i] in (0x30, 0x31):
        flag, tag, off, size = struct.unpack_from("<4I", d, i); i += 16
        out[tag & 0xFF] = (flag, tag, base + off, size)
    return d, out

def song_seqs(n):
    import os
    d = open(os.path.join(sep.EMI_DIR, f"BGM{n:03d}.EMI"), "rb").read()
    s = next(c for k, c in sep.emi_chunks(d) if k == 0x53455170)
    return {sid: (res, tempo, data) for sid, res, tempo, data in sep.songs(s)}

if __name__ == "__main__":
    n = int(sys.argv[1]); parts = [int(p) for p in sys.argv[2:]]
    d, pcs = pc_parts(n); seqs = song_seqs(n)
    for part in parts or sorted(pcs):
        flag, tag, off, size = pcs[part]
        if part not in seqs: continue
        x = decode(d[off:off + size]); pc = pc_env(x)
        ps, ls, le = ps1_env(*seqs[part])
        ratio, offs, sc = align(pc, ps)
        f = lambda t: None if t is None else round(offs + ratio * t, 2)
        print(f"BGM{n:03d} part{part}: PC {len(x)/44100:6.2f} s | ratio {ratio:.4f} offset {offs:+.2f} s score {sc:.2f} "
              f"| PS1 loop {ls and round(ls,2)}-{le and round(le,2)} -> PC {f(ls)}-{f(le)}")
