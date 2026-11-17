# Preview a bar-aligned jump for a recording that stops before its loop end: jump from E to a point at
# the same position within the bar (PS1 tempo/time signature, mapped onto the PC recording), choose the
# bar whose preceding music is most similar, fine-align on the beat, crossfade 60 ms.
#   py bar_preview.py BGM000/0
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
import json, struct, subprocess, sys, os, numpy as np
import align, measure, sep

FF = config.FFMPEG
SR, XF = 44100, int(0.06 * 44100)

key = sys.argv[1]; n, part = int(key[3:6]), int(key.split("/")[1])
v = json.load(open("loops.json"))[key]; t = json.load(open("loop_table.json"))[key]
d, pcs = align.pc_parts(n); flag, tag, off, size = pcs[part]
x = np.frombuffer(subprocess.run([FF, "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "2", "-ar", "44100", "pipe:1"],
                                 input=d[off:off + size], capture_output=True).stdout, "<i2").reshape(-1, 2).astype(np.float32)
mono = x.mean(1)

# tempo and time signature of the PS1 song (SEP header: id, resolution, tempo(3), rhythm(2), size)
emi = open(os.path.join(sep.EMI_DIR, f"BGM{n:03d}.EMI"), "rb").read()
sepd = next(c for k, c in sep.emi_chunks(emi) if k == 0x53455170)
i = 6
while True:
    sid, res = struct.unpack_from(">HH", sepd, i); tempo = int.from_bytes(sepd[i + 4:i + 7], "big")
    num, den_pow = sepd[i + 7], sepd[i + 8]; ln = struct.unpack_from(">I", sepd, i + 9)[0]
    if sid == part: break
    i += 13 + ln
beat = tempo / 1e6 * 4 / (2 ** den_pow)                 # seconds per beat of the time signature
bar = num * beat * v["ratio"]                           # one bar, in PC seconds
print(f"{key}: {60e6/tempo:.0f} bpm, {num}/{2**den_pow}, bar {bar:.3f} s; loop start {v['ls_pc']:.2f} s, file ends {t['E']/SR:.2f} s")

E = t["E"]; F = measure.frames(mono); h = measure.HOP; w = int(4 * SR / h)
def pre_sim(P):
    a, b = F[E // h - w:E // h], F[P // h - w:P // h]
    return float((a * b).sum(1).mean()) if len(b) == w else -1
cands = []
k = 1
while True:
    P = int(round(E - k * bar * SR))
    if P < (v["ls_pc"] + 0.0) * SR: break
    cands.append((pre_sim(P), P, k)); k += 1
min_loop = 0.7 * (v['le_ps1'] - v['ls_ps1']) * v['ratio'] * SR      # keep most of the song's real loop
cands = [c for c in cands if E - c[1] >= min_loop]
best = sorted(cands, reverse=True)[:3]
print("best bar-aligned targets (similarity of the 4 s before):", [(round(s, 3), round(P / SR, 2), kk) for s, P, kk in best])
s, P, kk = best[0]

# fine beat alignment: onset envelopes 2 s before E and before P, shift P by up to +-40 ms
def onsets(sig):
    hop = 220; m = len(sig) // hop
    e = np.log1p(np.abs(np.fft.rfft(sig[:m * hop].reshape(m, hop) * np.hanning(hop), axis=1))).sum(1)
    return np.maximum(0, np.diff(e))
ref = onsets(mono[E - 2 * SR:E])
shift = max(range(-1764, 1765, 22), key=lambda sh: float(np.dot(ref, onsets(mono[P + sh - 2 * SR:P + sh]))))
P += shift
print(f"jump {E/SR:.2f} s -> {P/SR:.2f} s (bar {kk} back, beat-aligned {shift/44.1:+.1f} ms)")

def jump_into(y_end, start):                             # crossfade the last XF samples before E into x[P-XF:P]
    w_ = np.sin(np.linspace(0, np.pi / 2, XF))[:, None] ** 2
    return np.concatenate([y_end[:-XF], y_end[-XF:] * (1 - w_) + x[start - XF:start] * w_])
y = np.concatenate([jump_into(x[:E], P), x[P:E]])
y = np.concatenate([jump_into(y, P), x[P:P + SR * 8]])
out = f"../music_check/loops/{key.replace('/', '_part')}_bar_aligned.mp3"
subprocess.run([FF, "-v", "error", "-y", "-f", "s16le", "-ar", "44100", "-ac", "2", "-i", "pipe:0", "-b:a", "192k", out],
               input=np.clip(y, -32768, 32767).astype("<i2").tobytes(), check=True)
s1 = E / SR; s2 = s1 + (E - P) / SR
print(f"preview: {out}\n  jumps at {int(s1//60)}:{s1%60:05.2f} and {int(s2//60)}:{s2%60:05.2f}")
