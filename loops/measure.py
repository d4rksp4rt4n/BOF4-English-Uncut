# Case A (recording runs past one loop): measure the true loop length from the audio itself
# (x(t) ~ x(t + L) over the repeated part), to sample precision, and compare with the PS1 prediction.
import json, os, numpy as np
import align
from selfsim import decode

HOP = 256

def frames(x):
    n = len(x) // HOP
    S = np.log1p(np.abs(np.fft.rfft(x[:n * HOP].reshape(n, HOP) * np.hanning(HOP), axis=1)))[:, 2:100]
    S -= S.mean(1, keepdims=True)
    return S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-9)

def loop_length(x, l_est, region, search=0.6):
    """lag in samples maximising similarity of x[t] and x[t+L] for t in region (seconds, second pass)."""
    F = frames(x); a0, a1 = int(region[0] * 44100 / HOP), int(region[1] * 44100 / HOP)
    best = (-1, 0)
    for lag in range(int((l_est - search) * 44100 / HOP), int((l_est + search) * 44100 / HOP)):
        if a0 - lag < 0: continue
        s = float((F[a0:a1] * F[a0 - lag:a1 - lag]).sum(1).mean())
        if s > best[0]: best = (s, lag)
    s, lag = best
    # sample-precise refinement: waveform cross-correlation around the frame estimate
    c0 = int(region[0] * 44100); w = min(int(region[1] * 44100) - c0, 44100 * 4)
    ref = x[c0:c0 + w]; best2 = (-1, lag * HOP)
    for L in range(lag * HOP - 2 * HOP, lag * HOP + 2 * HOP):
        seg = x[c0 - L:c0 - L + w]
        if len(seg) < w: continue
        r = float(np.dot(ref, seg) / (np.linalg.norm(ref) * np.linalg.norm(seg) + 1e-9))
        if r > best2[0]: best2 = (r, L)
    return s, best2[1], best2[0]

if __name__ == "__main__":
    res = json.load(open("loops.json"))
    for key, v in sorted(res.items()):
        if v.get("case") != "A": continue
        n, part = int(key[3:6]), int(key.split("/")[1])
        d, pcs = align.pc_parts(n); flag, tag, off, size = pcs[part]
        x = decode(d[off:off + size])
        l_est = v["le_pc"] - v["ls_pc"]
        region = (max(v["le_pc"], v["ls_pc"] + l_est) + 0.5, v["eof"] - 0.5)
        if region[1] - region[0] < 1.0: print(key, "too little repeat"); continue
        fs, L, wr = loop_length(x, l_est, region)
        v.update(L_meas=L, L_meas_s=L / 44100, frame_sim=round(fs, 3), wave_corr=round(wr, 4))
        print(f"{key}: PS1-predicted loop {l_est:7.3f} s, measured {L/44100:7.3f} s (diff {L/44100 - l_est:+.3f}), "
              f"spectral sim {fs:.2f}, waveform corr {wr:.3f}", flush=True)
    json.dump(res, open("loops.json", "w"), indent=1)
