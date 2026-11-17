# Identify screen: element icons for the weakness/resistance labels.
# The English release cut Identify because its Data panel draws the 12 element names one Japanese character
# apart (12 px), so "Fire", "Wind", "Water"... print on top of each other. navarchos' PS1 Identify hack
# replaced each name with an element icon; this does the same for the PC:
#   - INIT.DAT chunk 9 (font 1, the 12x17 text font: 24x24 4bpp cells, 104 glyphs) gets 12 more glyphs
#     (0x68-0x73), drawn from the PS1 system texture's element icons (12x12, colour set 13). The three the
#     US disc lacks (Wind, Holy, Mind) are navarchos' silhouettes from his hack.
#   - BOF4.exe: their metrics (u offset, advance) in the font 1 table (0x952EB0, 2 bytes per glyph). Slots
#     0x68-0xC9 are unused zeros; text chars 0x88-0x93 map to glyphs 0x68-0x73 (char - 0x20).
#   - AB000_00.DAT / BTLEND.DAT (battle text): the 12 label strings become one char each, padded with
#     zeros like the PS1 hack, so no offsets move.
# The panel picks the text colour per resistance (red weak, grey normal, blue strong); the glyph's pixel
# values index that colour's ramp (1 = full colour ... 8 = window background), as for letters.
#   py identify_icons.py    writes identify_icons.png (preview) and checks the build
import os, struct

LABELS = [b"Fire", b"Wind", b"Water", b"Earth", b"Holy", b"Mind", b"Stat", b"Death",
          b"Slash", b"Ranged", b"Magic", b"Dragon"]
FIRST_CHAR, FIRST_GLYPH = 0x88, 0x68
METRICS = 0x952EB0                     # font 1 glyph metrics (BOF4.exe .data)
FONT_CHUNK = 9                         # INIT.DAT chunk: type 5, dest 0x1801 (font 1, 24 px cells)

# 12x12 icons, 4bpp values in the PS1 icon colour set 13. Nine are the PS1/PC system texture's own element
# icons (byte-identical in the PC INIT.DAT); Wind, Holy and Mind are navarchos' (identify hack).
ICONS = """
......2..... ............ ............ ............ ............ ...11111.... ............ ............ ............ ............ ............ ....1.......
....211..... ............ .....1...... ....21112... ............ ...11111.... ...211112... ...211112... .1112....... ............ .21112...... ..1151......
...2141212.. ..11111..... ....161..... ...211bb12.. ..111..111.. ...11111.... ..212..212.. ..21111112.. .1331....... .112....211. .19791...... .15191......
...14311412. .1111111.... ...15611.... ..21adbba12. .1111111111. ............ ..12211221.. .2111111112. .14331...... .1211111111. .178712..... .191911.....
.2114741312. .1111111.... ..2166151... .211ddbbaa1. .1111111111. ...11111.... ..1.1221.1.. .112c11c211. .214331.211. .1321313131. .197111..... 15956151....
.1313334712. .1111111111. ..16661951.. .1addabada1. .1111111111. ...11111.... ..1.21.1.1.. .11c6116c11. ...14331151. .1321333331. .2111661.... 19656591....
.1343733312. .1111111111. .1211156511. .1bbabaddb1. ..11111111.. ...11111.... ..12..21.1.. .1122112211. ....1441512. .1211111662. ...211161... 19696995111.
.1437733412. .1111111111. .1555155211. .1bbabbbbb1. ...111111... .111111111.. ...1111.21.. .2111211112. .....11512.. .1121211661. .....16612.. 159566955551
.214373412.. .111111111.. .2151222112. ..11bbb1112. ....1111.... ..1111111... .......21... ..21111112.. ....216151.. ....2111661. ......1161.. .1556955511.
..2111112... ...111111... ..21122112.. ...2111112.. .....11..... ...11111.... .....211.... ...1c11c1... ....1512151. ......21661. .......2161. .11555511...
............ ............ ...211112... ............ ............ ....111..... .....1...... ...121121... ....112..11. .......1111. .........11. ...1111.....
............ ............ ............ ............ ............ .....1...... ............ ............ ............ ............ ............ ............
"""
# colour set 13 (INIT.DAT chunk 1, palette 13): RGB of each value, for shading
SET13 = [None, 0x585858, 0x908878, 0xF87018, 0xC83820, 0x6098F8, 0xF8F8F8, 0xD8E000,
         0x808000, 0xB0B8F8, 0xB08060, 0x986848, 0xB0B0A8, 0xD0A880, 0x00C858, 0x009028]

def icons():
    rows = [r.split() for r in ICONS.strip("\n").split("\n")]
    return [[[0 if c == "." else int(c, 16) for c in rows[y][i]] for y in range(12)] for i in range(len(LABELS))]

def luma(rgb): return (rgb >> 16) * 0.3 + (rgb >> 8 & 255) * 0.59 + (rgb & 255) * 0.11

def levels(ic):
    """Icon -> text-ramp values: darkest pixels (outlines) full colour (1), brightest 4. A flat silhouette
    (all one value) gets a full-colour edge and a lighter inside, like the shaded icons."""
    vals = {v for row in ic for v in row if v}
    if len(vals) == 1:
        inside = lambda x, y: 0 <= x < 12 and 0 <= y < 12 and ic[y][x]
        return [[0 if not ic[y][x] else (3 if all(inside(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                 else 1) for x in range(12)] for y in range(12)]
    lo, hi = min(luma(SET13[v]) for v in vals), max(luma(SET13[v]) for v in vals)
    return [[0 if not v else 1 + round(3 * (luma(SET13[v]) - lo) / (hi - lo)) for v in row] for row in ic]

def glyph(ic):
    """12x12 icon -> 24x24 4bpp font cell (288 bytes). A cell is drawn 12x17 on screen, letters use rows 3-19,
    so the icon is doubled across and stretched to 17 rows down to keep its shape."""
    lv = levels(ic)
    px = [[0] * 24 for _ in range(24)]
    for ty in range(17):
        for tx in range(24):
            px[3 + ty][tx] = lv[ty * 12 // 17][tx // 2]
    return bytes(px[y][x] | px[y][x + 1] << 4 for y in range(24) for x in range(0, 24, 2))

def table(d):
    n = struct.unpack_from("<I", d, 0)[0] // 16
    return [list(struct.unpack_from("<4I", d, i * 16)) for i in range(n)]

def patch_font(init):
    """INIT.DAT with the icon glyphs appended to font 1."""
    ents = table(init)
    o, s, f, t = ents[FONT_CHUNK]
    assert (f, t, s) == (5, 0x1801, 104 * 288), "INIT.DAT font chunk not as expected"
    add = b"".join(glyph(ic) for ic in icons())
    out = bytearray(init[:o + s] + add + init[o + s:])
    ents[FONT_CHUNK][1] += len(add)
    for e in ents[FONT_CHUNK + 1:]:
        e[0] += len(add)
    for i, e in enumerate(ents):
        struct.pack_into("<4I", out, i * 16, *e)
    return bytes(out)

def patch_labels(d):
    """Battle text (AB000_00 / BTLEND): each label string -> its icon char, zero padded."""
    d = bytearray(d)
    runs = [b"\0" + b"\0".join(LABELS[:8]) + b"\0", b"\0" + b"\0".join(LABELS[8:]) + b"\0"]
    assert all(d.count(r) == 1 for r in runs), "Identify labels not found"
    i, j = (d.find(r) for r in runs)
    k = 0
    for start, names in ((i + 1, LABELS[:8]), (j + 1, LABELS[8:])):
        for n in names:
            d[start:start + len(n)] = bytes([FIRST_CHAR + k]) + bytes(len(n) - 1)
            start += len(n) + 1; k += 1
    # HP separator (msg 0x73) and unknown-item mark (0x74) share one "?" (so HP read "123?456"); navarchos'
    # v1.1 fix: that string becomes "/", and 0x74 points at the "?" that ends another message.
    o, s = next((o, s) for o, s, f, t in table(d) if o < i < o + s)
    q = d.find(b"\0?\0READY\0", i) + 1
    base = next(b for b in (o, o + 8) if b + struct.unpack_from("<H", d, b + 0x73 * 2)[0] == q)
    assert all(base + struct.unpack_from("<H", d, base + m * 2)[0] == q for m in (0x72, 0x73, 0x74))
    other = next(p for p in range(base, o + s - 1) if d[p:p + 2] == b"?\0" and p != q and 0x20 < d[p - 1] < 0x7F)
    d[q] = ord("/")
    struct.pack_into("<H", d, base + 0x74 * 2, other - base)
    return bytes(d)

def patch_metrics(exe, fo):
    """BOF4.exe: metrics for the new glyphs (u offset 0, advance 24 = one 12 px cell)."""
    exe = bytearray(exe)
    a = fo(METRICS + FIRST_GLYPH * 2)
    assert exe[a:a + 2 * len(LABELS)] == bytes(2 * len(LABELS)), "font metric slots not free"
    exe[a:a + 2 * len(LABELS)] = b"\x00\x18" * len(LABELS)
    return bytes(exe)

# Treasure panel: an item not seen yet shows one "?" per letter of its name, 12 px apart (i*3*4), so long
# names run past the panel's edge (navarchos' v1.1 tightened this too). lea r,[eax+eax*2] -> [eax+eax]: 8 px.
UNKNOWN_STEP = [(0x607F5F, b"\x8d\x14\x40", b"\x8d\x14\x00"),    # steal slot: lea edx,[eax+eax*2]
                (0x608099, b"\x8d\x04\x40", b"\x8d\x04\x00")]    # drop slot:  lea eax,[eax+eax*2]

def patch_code(exe, fo):
    exe = bytearray(exe)
    for va, old, new in UNKNOWN_STEP:
        assert exe[fo(va):fo(va) + 3] == old, f"unexpected code at {va:#x}"
        exe[fo(va):fo(va) + 3] = new
    return bytes(exe)

def preview(path):
    from PIL import Image
    ramps = {"weak": [0xA05050, 0x985850, 0x986050, 0x986858, 0x987058, 0x987860, 0x988868, 0x989878],
             "normal": [0x606068, 0x686868, 0x707068, 0x787868, 0x808070, 0x888870, 0x909070, 0x989878],
             "strong": [0x4870A0, 0x507098, 0x587890, 0x688088, 0x708080, 0x788880, 0x889078, 0x989878]}
    Z = 6
    im = Image.new("RGB", (len(LABELS) * 14 * Z, 3 * 20 * Z), (0x98, 0x98, 0x78))
    for r, ramp in enumerate(ramps.values()):
        for i, ic in enumerate(icons()):
            g = glyph(ic)
            cell = Image.new("RGB", (24, 24), (0x98, 0x98, 0x78))
            for p in range(576):
                v = g[p // 2] >> (4 * (p & 1)) & 15
                if v: c = ramp[v - 1]; cell.putpixel((p % 24, p // 24), (c >> 16, c >> 8 & 255, c & 255))
            im.paste(cell.resize((12 * Z, 17 * Z), Image.BILINEAR).crop((0, 0, 12 * Z, 17 * Z)),
                     ((i * 14 + 1) * Z, (r * 20 + 1) * Z))
    im.save(path)

if __name__ == "__main__":
    import config
    here = os.path.dirname(os.path.abspath(__file__))
    preview(os.path.join(here, "identify_icons.png"))
    init = open(os.path.join(config.CLEAN_DAT, "INIT.DAT"), "rb").read()
    new = patch_font(init)
    assert table(new)[FONT_CHUNK][1] == 116 * 288
    for f in ("AB000_00.DAT", "BTLEND.DAT"):
        d = open(os.path.join(config.CLEAN_DAT, f), "rb").read()
        p = patch_labels(d)
        assert len(p) == len(d) and sum(a != b for a, b in zip(d, p)) <= sum(map(len, LABELS)) + 3
    print("ok; preview in identify_icons.png")
