# BOF4 PC chunk compression (DAT chunk type 1): LZHUF variant, decoder at BOF4.exe 0x691AF0.
# Adaptive Huffman over 321 symbols (0-255 literal, 256+ = match length sym-253), LSB-first bit order,
# 12-bit distance (upper 6 bits via fixed d_code/d_len tables, lower 6 raw), copy from out[-1-d],
# d == 0xFFF ends the stream. The model's start state is copied from the exe (0x962260).
import struct

T2, R2 = 0x502, 0x500                        # tree size / root, as byte offsets (the exe indexes words *2)
FREQ, SON, PRNT = 0, 0x504, 0xA06            # table offsets inside the state blob (exe 0x9633EC)
_exe = None

def _tables(exe):
    def fo(va): return va - 0x8D4000 + 0x2BE200
    state = exe[fo(0x962260):fo(0x962260) + 0x463 * 4]
    d_code = exe[fo(0x962060):fo(0x962060) + 256]
    d_len = exe[fo(0x962160):fo(0x962160) + 256]
    return state, d_code, d_len

class _Model:
    def __init__(self, state): self.m = bytearray(state)
    def w(self, o): return struct.unpack_from("<H", self.m, o)[0]
    def sw(self, o, v): struct.pack_into("<H", self.m, o, v & 0xFFFF)
    def update(self, c2, check=True):        # c2 = symbol * 2   (exe 0x691BB9 / 0x691BCD)
        if check and self.w(FREQ + R2) == 0x8000: self.reconstruct()
        bx = self.w(PRNT + T2 + c2)
        while True:
            self.sw(FREQ + bx, self.w(FREQ + bx) + 1)
            f = self.w(FREQ + bx)
            if f > self.w(FREQ + bx + 2):
                l = bx + 2
                while l + 2 < FREQ + SON and self.w(FREQ + l + 2) == f - 1: l += 2
                self.sw(FREQ + bx, self.w(FREQ + l)); self.sw(FREQ + l, f)
                i, j = self.w(SON + bx), self.w(SON + l)
                self.sw(PRNT + j, bx)
                if j < T2: self.sw(PRNT + j + 2, bx)
                self.sw(PRNT + i, l)
                if i < T2: self.sw(PRNT + i + 2, l)
                self.sw(SON + bx, j); self.sw(SON + l, i)
                bx = l
            bx = self.w(PRNT + bx)
            if bx == 0: return
    def reconstruct(self):                   # exe 0x691B7C
        for c2 in range(0, 0x141 * 2, 2):
            if self.w(FREQ + self.w(PRNT + T2 + c2)) & 1: self.update(c2, check=False)
        for o in range(0, T2 + 2, 2): self.sw(FREQ + o, self.w(FREQ + o) >> 1)

def decompress(src, exe):
    state, d_code, d_len = _tables(exe)
    m, out, pos = _Model(state), bytearray(), 0
    src = bytes(src) + b"\0" * 8
    bit = lambda p: (src[p >> 3] >> (p & 7)) & 1
    while True:
        bx = m.w(SON + R2)
        while bx < T2:
            bx = m.w(SON + bx + 2 * bit(pos)); pos += 1
        c2 = bx - T2
        m.update(c2)
        c = c2 >> 1
        if c < 256: out.append(c); continue
        v = struct.unpack_from("<I", src, pos >> 3)[0] >> (pos & 7)
        idx = v & 0xFF; n = d_len[idx]
        d = (d_code[idx] << 6) | ((v >> n) & 0x3F)
        pos += n + 6
        if d == 0xFFF: return bytes(out)
        for _ in range(c - 253): out.append(out[-1 - d])

def compress(data, exe):
    state, d_code, d_len = _tables(exe)
    upper = {}                               # upper 6 bits -> (code, length), LSB-first
    for idx in range(256):
        upper.setdefault(d_code[idx], (idx & ((1 << d_len[idx]) - 1), d_len[idx]))
    m, bits = _Model(state), []
    def put(v, n): bits.extend((v >> k) & 1 for k in range(n))
    def sym(c):
        path, k = [], m.w(PRNT + T2 + 2 * c)
        while k != R2:
            path.append((k >> 1) & 1); k = m.w(PRNT + k)
        bits.extend(reversed(path)); m.update(2 * c)
    def dist(d):
        put(*upper[d >> 6]); put(d & 0x3F, 6)
    heads, i = {}, 0
    while i < len(data):
        best, bd = 0, 0
        for j in reversed(heads.get(data[i:i + 3], [])[-64:]):
            if i - j > 0xFFF: break
            n = 0
            while n < 67 and i + n < len(data) and data[j + n] == data[i + n]: n += 1
            if n > best: best, bd = n, i - j - 1
            if n == 67: break
        if best >= 3:
            sym(best + 253); dist(bd); step = best
        else:
            sym(data[i]); step = 1
        for k in range(i, i + step): heads.setdefault(data[k:k + 3], []).append(k)
        i += step
    sym(256); dist(0xFFF)
    out = bytearray((len(bits) + 7) // 8)
    for k, b in enumerate(bits): out[k >> 3] |= b << (k & 7)
    return bytes(out)

if __name__ == "__main__":                   # self-check against a real chunk
    import os, config
    exe = open(config.CLEAN_EXE, "rb").read()
    d = open(os.path.join(config.CLEAN_DAT, "INIT.DAT"), "rb").read()
    raw = decompress(d[0xC0:0xC0 + 0x23E6], exe)
    assert len(raw) == 0x8000, hex(len(raw))
    assert decompress(compress(raw, exe), exe) == raw
    print("lzhuf ok", len(compress(raw, exe)), "vs original", 0x23E6)
