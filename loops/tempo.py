# Estimate a PC track's tempo from its onset envelope (autocorrelation), to compare with the PS1 SEQ tempo.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config, os
import struct, sys, numpy as np
from selfsim import decode
import sep

def onset_env(x, hop=441):                                  # 10 ms hops
    n = len(x) // hop
    fr = x[:n * hop].reshape(n, hop)
    e = np.log1p(np.abs(np.fft.rfft(fr * np.hanning(hop), axis=1)))
    flux = np.maximum(0, np.diff(e, axis=0)).sum(1)
    return flux - flux.mean()

def tempo(x, lo=60, hi=200):
    o = onset_env(x); ac = np.correlate(o, o, "full")[len(o) - 1:]
    lags = np.arange(len(ac)); bpm = 6000.0 / np.maximum(lags, 1)
    ok = (bpm >= lo) & (bpm <= hi)
    best = lags[ok][np.argmax(ac[ok])]
    # refine with parabolic interpolation
    a, b, c = ac[best - 1], ac[best], ac[best + 1]
    lag = best + 0.5 * (a - c) / (a - 2 * b + c)
    return 6000.0 / lag

if __name__ == "__main__":
    n = int(sys.argv[1])
    d = open(os.path.join(config.CLEAN_DAT, f"BGM{n:03d}.DAT"), "rb").read()[0x10:]
    ps1 = {sid: (ls, le, tot) for sid, ls, le, tot in sep.bgm_loops(n)}
    i = 0
    while d[i] in (0x30, 0x31):
        flag, tag, off, size = struct.unpack_from("<4I", d, i); i += 16
        x = decode(d[off:off + size]); part = tag & 0xFF
        print(f"BGM{n:03d} part{part}: PC {len(x)/44100:6.2f} s, est. tempo {tempo(x):6.1f} bpm | table bpm {(tag >> 16) & 0xFF} | PS1 loop {ps1.get(part)}")
