# Does a PC music stream contain a repeat? Decode with ffmpeg, build coarse log-spectrum frames and look
# for the lag at which the end of the track best matches earlier audio.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
import subprocess, sys, numpy as np
FF = config.FFMPEG
HOP = 1024                                   # ~23 ms at 44.1 kHz

def decode(mp3_bytes):
    p = subprocess.run([FF, "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", "44100", "pipe:1"],
                       input=mp3_bytes, capture_output=True, check=True)
    return np.frombuffer(p.stdout, "<i2").astype(np.float32)

def features(x):
    n = len(x) // HOP
    fr = x[:n * HOP].reshape(n, HOP) * np.hanning(HOP)
    S = np.log1p(np.abs(np.fft.rfft(fr, axis=1))[:, 4:300])        # ~170 Hz .. 13 kHz
    S -= S.mean(1, keepdims=True)
    return S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-9)

def best_repeat(F, tail_s=6.0):
    """lag (frames) at which the last tail_s seconds best match earlier audio, with its similarity."""
    t = int(tail_s * 44100 / HOP); tail = F[-t:]
    best = (0, -1)
    for lag in range(t, len(F) - t):
        sim = float((F[-t - lag:-lag] * tail).sum(1).mean())
        if sim > best[1]: best = (lag, sim)
    return best

if __name__ == "__main__":
    import struct
    for path in sys.argv[1:]:
        d = open(path, "rb").read()[0x10:]
        i = 0
        while d[i] in (0x30, 0x31):
            flag, tag, off, size = struct.unpack_from("<4I", d, i); i += 16
            x = decode(d[off:off + size]); F = features(x)
            lag, sim = best_repeat(F)
            print(f"{path[-10:]} part{tag & 0xff} loop={flag & 1} len={len(x)/44100:6.1f}s  best repeat lag {lag*HOP/44100:6.1f}s  sim {sim:.2f}")
