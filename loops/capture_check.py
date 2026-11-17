# Line a loopback recording of the fishing scene up against the clean fishing song (BGM010/1 with our
# loop points) and report where the playback departs from it: gaps, skips, repeats, timing jumps.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
import struct, sys, numpy as np, subprocess
import align

FF = config.FFMPEG
SR = 44100

def read_wav(p):
    d = open(p, "rb").read()
    i, fmt = 12, None
    while i < len(d):
        cid, n = d[i:i + 4], struct.unpack_from("<I", d, i + 4)[0]
        if cid == b"fmt ": fmt = struct.unpack_from("<HHIIHH", d, i + 8)
        if cid == b"data": return fmt, d[i + 8:i + 8 + n] if n else d[i + 8:]   # size 0: recorder not finalised
        i += 8 + n
    raise ValueError("no data")

fmt, raw = read_wav(sys.argv[1])
tag, ch, sr, _, align_b, bits = fmt
assert sr == SR and bits == 32, fmt
cap = np.frombuffer(raw[:len(raw) // align_b * align_b], "<f4").reshape(-1, ch)[:, :2].mean(1)

d, pcs = align.pc_parts(10); flag, tag2, off, size = pcs[1]
x = np.frombuffer(subprocess.run([FF, "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", "44100", "pipe:1"],
                                 input=d[off:off + size], capture_output=True).stdout, "<i2").astype(np.float32) / 32768
E, P = 3330432, 1479
ref = np.concatenate([x[:E]] + [x[P:E]] * 6)

def xcorr_best(a, b):                       # best lag of a inside b (len(b) >= len(a)), normalised score
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)[:len(b) - len(a) + 1]
    k = int(np.argmax(c))
    return k, c[k] / (np.linalg.norm(a) * np.linalg.norm(b[k:k + len(a)]) + 1e-9)

# initial position: a 4 s chunk from 5 s in, searched over the whole first pass + a bit
c0 = 5 * SR
k, s = xcorr_best(cap[c0:c0 + 4 * SR], ref[:E + 10 * SR])
offset = k - c0                             # ref index = capture index + offset
print(f"capture {len(cap)/SR:.1f} s; song position at capture start {offset/SR:+.3f} s (match {s:.2f})")

W, H, SEARCH = SR // 4, SR // 10, SR // 2     # 0.25 s windows every 0.1 s, search +-0.5 s
events, prev = [], offset
for t in range(0, len(cap) - W, H):
    a = cap[t:t + W]
    if np.abs(a).max() < 1e-3: events.append((t, "silence", 0)); continue
    lo = max(0, t + prev - SEARCH); b = ref[lo:t + prev + SEARCH + W]
    k, s = xcorr_best(a, b)
    off = lo + k - t
    if s > 0.6 and abs(off - prev) > 20:                       # >0.45 ms jump in timing
        events.append((t, "jump", off - prev)); prev = off
    elif s < 0.4:
        events.append((t, "mismatch", round(s, 2)))
    elif s > 0.6:
        prev = off
for t, kind, v in events:
    if kind == "jump":
        print(f"{int(t/SR)//60}:{t/SR%60:05.2f}  timing jump {v/SR*1000:+8.1f} ms  ({'audio skipped ahead' if v > 0 else 'audio repeated / paused'})")
    else:
        print(f"{int(t/SR)//60}:{t/SR%60:05.2f}  {kind} {v}")
