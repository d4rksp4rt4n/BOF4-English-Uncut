# Derives the event-script redirects in patch_uncut_en.py (DIVERTS) from the PS1 discs and BOF4.exe.
#   py derive_scenes.py      prints the table and checks it against patch_uncut_en.DIVERTS
#
# Needs the clean US PS1 disc (config.PS1_US_BIN) and navarchos' "Uncensored" hack, extracted
# (config.PS1_HACK_WORLD). Each area's event scripts sit in its overlay chunk (EMI chunk loaded at
# 0x801F0800). Diffing that chunk, US vs hack, shows the US release cut the scenes by inserting early
# script ends (opcode c4, which never advances) and skips; every other difference is the hack's
# pointers and alignment shifting after its inserts. The PC exe holds the same script bytes in .data,
# found here by matching the US chunk. Instead of moving anything, the exe's fetch hook jumps:
#   trigger -> insert (the hack's bytes) -> resume, or trigger -> resume for a deletion.
# A trigger must be an instruction start: the edits begin right after 1-byte ops (c2, 17) or a
# c4 end. Opcode lengths used, from the exe's interpreter (0x4BC7FD): 17 = 1, 18 xx = 2, d0 a b = 3,
# 14 = 1, c4 = end.
import difflib, os, struct, sys
import config
from patch_uncut_en import DATA_VA, DATA_RAW, DIVERTS

OVERLAY = 0x801F0800

def iso_files(path):
    f = open(path, "rb")
    def read(lba, size):
        out = bytearray()
        while len(out) < size:
            f.seek(lba * 2352 + 24); out += f.read(2048); lba += 1
        return bytes(out[:size])
    files = {}
    def walk(lba, size, path):
        d, i = read(lba, size), 0
        while i < len(d):
            if d[i] == 0: i = (i // 2048 + 1) * 2048; continue
            elba, esize = struct.unpack_from("<I", d, i + 2)[0], struct.unpack_from("<I", d, i + 10)[0]
            name = d[i + 33:i + 33 + d[i + 32]].decode("latin1").split(";")[0]
            if name not in ("\0", "\1"):
                if d[i + 25] & 2: walk(elba, esize, path + name + "/")
                else: files[path + name] = (elba, esize)
            i += d[i]
    root = read(16, 2048)[156:190]
    walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
    return lambda name: read(*files[name])

def overlay(emi):
    n, off = struct.unpack_from("<I", emi)[0], 0x800
    for i in range(n):
        size, dest = struct.unpack_from("<2I", emi, 16 + 16 * i)
        if dest == OVERLAY: return emi[off:off + size]
        off = (off + size + 0x7FF) & ~0x7FF

def pc_base(us, exe):
    """VA where the exe holds this overlay's data: the offset most unique 12-byte runs agree on."""
    votes = {}
    for x in range(0, len(us) - 12, 4):
        run = us[x:x + 12]
        if len(set(run)) < 5: continue
        i = exe.find(run, DATA_RAW)
        if i >= 0 and exe.find(run, i + 1) < 0:
            b = i - DATA_RAW + DATA_VA - x
            votes[b] = votes.get(b, 0) + 1
    return max(votes, key=votes.get)

# (area, US offset, US end, hack start, hack end, kind) from the diff; the asserts below re-check them.
EDITS = [
    ("AREAM031", 0x17F9, 0x17F9, 0x17F9, 0x1811, "insert"),   # Ryu/Ursula at the checkpoint
    ("AREAM031", 0x1CA7, 0x1CA8, 0x1CBF, 0x1CBF, "delete"),   # early end (c4) before the rest of it
    ("AREAM027", 0x110A, 0x1126, 0x110A, 0x110A, "delete"),   # Ursula on Zig's ship: skip block
    ("AREAD157", 0x4303, 0x4315, 0x4303, 0x432C, "replace"),  # Soniel vs Fou-Lu, both end in c4
]

def derive():
    us_disc = iso_files(config.PS1_US_BIN)
    exe = open(config.CLEAN_EXE, "rb").read()
    out, cache = [], {}
    for area, a0, a1, b0, b1, kind in EDITS:
        if area not in cache:
            us = overlay(us_disc("BIN/WORLD/%s.EMI" % area))
            hack = overlay(open(os.path.join(config.PS1_HACK_WORLD, area + ".EMI"), "rb").read())
            cache[area] = us, hack, pc_base(us, exe)
        us, hack, base = cache[area]
        tail = 1 if kind == "replace" else 32       # after a replaced scene's end only padding differs
        assert us[a0 - 8:a0] == hack[b0 - 8:b0] and us[a1:a1 + tail] == hack[b1:b1 + tail], (area, hex(a0))
        if kind == "insert":            # the hack adds code before the instruction at a0 (18 xx, 2 bytes):
            assert us[a0] == 0x18       # run the insert plus that instruction, then continue after it
            trig, ins, resume = a0, hack[b0:b1 + 2], a0 + 2
        elif kind == "delete":
            trig, ins, resume = a0, None, a1
        else:                           # replaced up to the scene's end: run the hack's version, end on US c4
            assert us[a1] == hack[b1] == 0xC4
            trig, ins, resume = a0, hack[b0:b1], a1
        check = (min(trig, resume) - 4, max(trig, resume) + 4)
        o = base + check[0] - DATA_VA + DATA_RAW
        assert exe[o:o + check[1] - check[0]] == us[check[0]:check[1]], (area, "PC bytes differ")
        out.append((base + trig, ins, base + resume, base + check[0], us[check[0]:check[1]], area))
    return out

if __name__ == "__main__":
    t = derive()
    for trig, ins, resume, va, orig, area in t:
        print("    (%#x, %s, %#x, %#x, H(\"%s\")),  # %s" % (
            trig, 'H("%s")' % ins.hex() if ins else "None", resume, va, orig.hex(), area))
    same = [x[:5] for x in t] == [tuple(d) for d in DIVERTS]
    print("matches patch_uncut_en.DIVERTS" if same else "DIFFERS from patch_uncut_en.DIVERTS")
    sys.exit(0 if same else 1)
