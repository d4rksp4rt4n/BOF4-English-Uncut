# Musical match for recordings that still restart from the beginning ("restart" in loop_table.json):
# find an earlier point P whose preceding music matches the music before the end E (4 s and 8 s windows,
# spectral frames), refine to the sample, and jump E -> P instead. A seamless jump needs only that the
# music leading into both points is the same. Where we trust the PS1 loop start, P must lie after it.
import json, numpy as np
import align, measure
from selfsim import decode

SR, HOP = 44100, measure.HOP
W1, W2, LMIN, WAVE = 4.0, 8.0, 10.0, 0.60

def window_sim(F, e, w):
    """sim[p] = mean over the w frames before p of dot(F[p-w+i], F[e-w+i]), for every p (FFT per bin)."""
    T = F[e - w:e]; n = len(F)
    m = 1 << int(np.ceil(np.log2(n + w)))
    acc = np.zeros(n - w + 1)
    for b in range(F.shape[1]):
        c = np.fft.irfft(np.fft.rfft(F[:, b], m) * np.conj(np.fft.rfft(T[:, b], m)), m)[:n - w + 1]
        acc += c
    sim = np.full(n + 1, -1.0); sim[w:n + 1] = acc / w       # index = frame where the window ends
    return sim

def refine(x, E, P, span=2 * HOP, w=8192):
    ref = x[E - w:E]; best = (-2.0, P)
    for k in range(P - span, P + span + 1):
        seg = x[k - w:k]
        r = float(np.dot(ref, seg) / (np.linalg.norm(ref) * np.linalg.norm(seg) + 1e-9))
        if r > best[0]: best = (r, k)
    return best[1], best[0]

res = json.load(open("loops.json")); table = json.load(open("loop_table.json"))
done = 0
for key, t in sorted(table.items()):
    if t["how"] != "restart": continue
    v = res[key]; n, part = int(key[3:6]), int(key.split("/")[1])
    d, pcs = align.pc_parts(n); flag, tag, off, size = pcs[part]
    x = decode(d[off:off + size]); F = measure.frames(x)
    E = t["E"]; e = E // HOP
    s1, s2 = window_sim(F, e, int(W1 * SR / HOP)), window_sim(F, e, int(W2 * SR / HOP))
    lo = int(t["P"] / HOP) + int(W1 * SR / HOP)                  # after the first sound + window
    if v.get("score", 0) >= 0.15: lo = max(lo, int((v["ls_pc"] - 0.05) * SR / HOP))   # trusted loop start
    hi = e - int(LMIN * SR / HOP)
    if hi <= lo: print(key, "too short to search"); continue
    both = np.minimum(s1, s2)[lo:hi]
    # spectral similarity alone is not discriminative (same instruments look ~0.9 alike everywhere):
    # take its best local peaks and keep the one whose waveform before the jump really matches
    peaks = [i for i in range(1, len(both) - 1) if both[i] >= 0.85 and both[i] >= both[i - 1] and both[i] >= both[i + 1]]
    peaks = sorted(peaks, key=lambda i: -both[i])[:20]
    cands = []
    for i in peaks:
        P, wc = refine(x, E, (lo + i) * HOP)
        cands.append((wc, P, float(both[i])))
    if not cands or max(c[0] for c in cands) < WAVE:
        print(f"{key}: best waveform match {max((c[0] for c in cands), default=0):.2f} - kept as restart"); continue
    wc, P, best = max(cands)
    t.update(P=int(P), L=int(E - P), how="matched", sim=round(best, 3), wave=round(wc, 3))
    done += 1
    print(f"{key}: jump {E/SR:7.2f} s -> {P/SR:7.2f} s (loop {(E-P)/SR:6.2f} s, PS1 loop {v.get('le_ps1',0)-v.get('ls_ps1',0):6.2f} s), "
          f"match {best:.2f}, waveform {wc:.2f}", flush=True)
json.dump(table, open("loop_table.json", "w"), indent=1)
print(done, "matched")
