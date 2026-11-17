# Classify every looping PC music stream against its PS1 sequence and estimate loop points.
#   A: recording runs past one full loop  -> loop length measurable in the audio itself
#   B: recording ends at the PS1 loop end -> loop start from the PS1 data
#   C: recording stops before the loop end
# Output: loops.json {"BGMnnn/part": {...}}
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
import glob, json, os, struct, sys, numpy as np
import align
from selfsim import decode

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loops.json")

def fine_align(pc, ps):
    a = align.smooth(pc - pc.mean()); na = np.linalg.norm(a)
    def score(ratio):
        idx = (np.arange(int(len(ps) * ratio)) / ratio).astype(int); b = align.smooth(ps[idx]); b = b - b.mean()
        n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
        c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
        lags = np.r_[0:500, n - 500:n]; k = lags[np.argmax(c[lags])]
        return c[k] / (na * np.linalg.norm(b) + 1e-9), (k if k < n // 2 else k - n) / align.RATE
    best = max((score(r) + (r,) for r in np.arange(0.985, 1.015, 0.001)), key=lambda t: t[0])
    best = max((score(r) + (r,) for r in np.arange(best[2] - 0.001, best[2] + 0.001, 0.0001)), key=lambda t: t[0])
    return best[2], best[1], best[0]                        # ratio, offset, score

def main():
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for path in sorted(glob.glob(os.path.join(config.CLEAN_DAT, "BGM*.DAT"))):
        n = int(os.path.basename(path)[3:6])
        try: seqs = align.song_seqs(n)
        except Exception: continue
        d, pcs = align.pc_parts(n)
        for part, (flag, tag, off, size) in sorted(pcs.items()):
            key = f"BGM{n:03d}/{part}"
            if key in res or not flag & 1 or part not in seqs: continue
            x = decode(d[off:off + size]); eof = len(x) / 44100
            ps, ls, le = align.ps1_env(*seqs[part])
            if ls is None or le is None:
                res[key] = {"case": "no PS1 loop", "eof": eof}; continue
            ratio, offset, sc = fine_align(align.pc_env(x), ps)
            ls_pc, le_pc = offset + ratio * ls, offset + ratio * le
            case = "A" if eof > le_pc + 2 else "B" if eof > le_pc - 2 else "C"
            res[key] = dict(case=case, eof=eof, ratio=ratio, offset=offset, score=round(sc, 3),
                            ls_ps1=ls, le_ps1=le, ls_pc=ls_pc, le_pc=le_pc, size=size, off=off)
            print(key, case, f"eof {eof:.2f} loop {ls_pc:.2f}-{le_pc:.2f} ratio {ratio:.4f} score {sc:.2f}", flush=True)
            json.dump(res, open(OUT, "w"), indent=1)

if __name__ == "__main__":
    main()
