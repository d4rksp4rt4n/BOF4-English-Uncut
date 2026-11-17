# Decide each looping stream's loop (E: sample where to leave, P: sample to continue at).
#   measured  - the recording holds more than one pass: E = end of the music, P = E - L (L measured)
#   exact     - the recording ends at the loop end (PS1 timing): E = end of the music (no encoder
#               padding), P = E - L (L from PS1), never into the silent lead-in
# The last MP3 frame of a file is never played: the game's decoder garbles it (a crackle at the loop).
#   tail      - the recording runs on past the loop end with something that is not the next pass:
#               E = mapped loop end, P = mapped loop start
#   from start - the loop covers the whole recording (PS1 loop start < 0.1 s): E = end, P = first sound
#   restart   - no reliable loop point (yet): restart from the first sound, as the game does, but without
#               the garbled final frame and the silent padding
import json, collections, numpy as np
import align
from selfsim import decode

SR = 44100
res = json.load(open("loops.json"))
table, why = {}, collections.Counter()

def music_bounds(x):
    nz = np.nonzero(np.abs(x) > 64)[0]
    return int(nz[0]), int(nz[-1]) + 1

def repeats(x, a, b, lag):
    """similarity of x[a:b] with x[a-lag:b-lag] (spectral frames); ~0.9+ means the same music"""
    import measure
    F = measure.frames(x); h = measure.HOP
    a, b, lag = a // h, b // h, lag // h
    if b - a < 4 or a - lag < 0: return 0.0
    return float((F[a:b] * F[a - lag:b - lag]).sum(1).mean())

def restart(key, v, end, head, reason):
    """No reliable loop point yet: keep the game's restart from the beginning, but skip the garbled
    final frame and the encoder's silent padding at both ends (the click/gap on every restart)."""
    table[key] = dict(size=v["size"], E=int(end), P=int(head), L=int(end - head), how="restart")
    why["restart without gap/click (" + reason + ")"] += 1

for key, v in sorted(res.items()):
    if "ratio" not in v: why["no PS1 loop data"] += 1; continue
    n, part = int(key[3:6]), int(key.split("/")[1])
    d, pcs = align.pc_parts(n); flag, tag, off, size = pcs[part]
    x = decode(d[off:off + size]); head, end = music_bounds(x)
    end = min(end, (len(x) // 1152 - 1) * 1152)          # the game's decoder garbles a file's final frame
    ls, le = round(v["ls_pc"] * SR), round(v["le_pc"] * SR)
    if v["ls_ps1"] < 0.1 and v.get("frame_sim", 0) < 0.9:    # loops over the whole recording: no alignment needed
        table[key] = dict(size=v["size"], E=int(end), P=int(head), L=int(end - head), how="from start")
        why["fixed (loops from the start)"] += 1; continue
    if v.get("frame_sim", 0) >= 0.9:
        E, L, how = end, v["L_meas"], "measured"
    elif v["score"] < 0.08 or (v["score"] < 0.15 and abs(end - le) > 0.1 * SR):
        restart(key, v, end, head, "alignment too weak"); continue
    elif abs(end - le) <= 0.15 * SR:
        E, L, how = end, le - ls, "exact"
    elif end > le:
        if repeats(x, le + 2048, end - 1024, le - ls) >= 0.85: E, L, how = end, le - ls, "exact"
        else: E, L, how = le, le - ls, "tail"
    else:
        restart(key, v, end, head, "recording stops before the loop end"); continue
    P = max(E - L, head)
    if P < ls - 0.05 * SR and P != head:
        restart(key, v, end, head, "recording stops before the loop end"); continue
    table[key] = dict(size=v["size"], E=int(E), P=int(P), L=int(L), how=how)
    why["fixed (" + how + ")"] += 1
json.dump(table, open("loop_table.json", "w"), indent=1)
for k, c in why.most_common(): print(f"{c:4d}  {k}")
