/* BOF4 PC: correct music loop points.
 * The PC music player restarts a looping MP3 from byte 0 at its end (0x40FDF3: seek(dec, 0)), so every
 * intro replays, and many recordings do not end at the loop point. loops_table.h (from build_mod.py /
 * loops/final.py) gives, per recording, E: the sample where to leave and P = E - one loop length.
 * BOF4.exe calls bof4_new_decoder instead of 0x40FD20 and bof4_decode instead of 0x695030; for a known
 * recording the decode wrapper jumps from E to P itself (seek a few frames earlier, drop the decoder's
 * warm-up samples) and keeps handing the game whole 1152-sample frames, so the game never reaches EOF.
 */
#include <windows.h>
#include <string.h>

typedef void *(__cdecl *newdec_t)(const unsigned char *mp3, int size);
typedef int (__stdcall *decode_t)(void *dec, short *out);
typedef int (__stdcall *seek_t)(void *dec, unsigned pos);
#define ORIG_NEWDEC ((newdec_t)0x0040FD20)
#define ORIG_DECODE ((decode_t)0x00695030)
#define ORIG_SEEK   ((seek_t)0x00693F90)
#define PRODUCED(dec) (*(int *)(*(char **)((char *)(dec) + 0x14) + 8))      /* bytes from last decode */
#define DEC_EOF ((int)0xFFFFFDFE)
#define FRAME 1152
#define WARMUP 3                                   /* frames decoded and dropped after a seek */
#define MAXDEC 16
#define DECLICK 256                                /* samples (~6 ms) over which a jump's step is faded out */

typedef struct { int size; unsigned crc; int E, P; } Loop;
#include "loops_table.h"                           /* static const Loop LOOPS[]; */
#pragma comment(linker, "/EXPORT:bof4_decode=_bof4_decode@8")   /* undecorated name for GetProcAddress */

typedef struct {
    void *dec; const unsigned char *mp3; int size;
    const Loop *loop;
    int pos, discard;                              /* pos: next kept sample, in the stream's timeline */
    short fifo[2 * FRAME * 3]; int fifo_n;         /* stereo frames waiting to be handed out */
    int last[2], delta[2], ramp;                   /* de-click after a jump */
} Stream;
static Stream g_st[MAXDEC];
static CRITICAL_SECTION g_cs;
static int g_loops_on, g_next;
#define STAT_MATCHED (*(volatile int *)0x006A7B14)   /* spare bytes in the exe stub's data: test counters */
#define STAT_JUMPS   (*(volatile int *)0x006A7B18)
#define STAT_LASTSZ  (*(volatile int *)0x006A7B1C)
static HANDLE g_dump = INVALID_HANDLE_VALUE;   /* ini dump=1: write looped streams' output (testing) */

static unsigned crc32(const unsigned char *p, int n) {
    unsigned c = 0xFFFFFFFFu; int i, k;
    for (i = 0; i < n; i++) { c ^= p[i]; for (k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1))); }
    return ~c;
}

static unsigned frame_offset(const unsigned char *m, int size, int frame) {  /* MPEG-1 Layer III, CBR or VBR */
    static const int BR[16] = {0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0};
    unsigned i = 0; int f = 0;
    while (f < frame && i + 4 <= (unsigned)size && m[i] == 0xFF && (m[i + 1] & 0xE0) == 0xE0) {
        int br = BR[m[i + 2] >> 4], pad = (m[i + 2] >> 1) & 1;
        if (!br) break;
        i += 144000 * br / 44100 + pad; f++;
    }
    return i;
}

static Stream *find(void *dec) {
    int i;
    for (i = 0; i < MAXDEC; i++) if (g_st[i].dec == dec) return &g_st[i];
    return 0;
}

__declspec(dllexport) void *__cdecl bof4_new_decoder(const unsigned char *mp3, int size) {
    void *dec = ORIG_NEWDEC(mp3, size);
    Stream *s; int i; unsigned crc;
    if (!dec || !g_loops_on) return dec;
    EnterCriticalSection(&g_cs);
    if (!(s = find(dec))) s = &g_st[g_next++ % MAXDEC];  /* the game has at most 7 decoders alive */
    {
        memset(s, 0, sizeof *s);
        crc = crc32(mp3, size < 4096 ? size : 4096);
        STAT_LASTSZ = size;
        for (i = 0; i < (int)(sizeof LOOPS / sizeof LOOPS[0]); i++)
            if (LOOPS[i].size == size && LOOPS[i].crc == crc) { s->loop = &LOOPS[i]; STAT_MATCHED++; break; }
        s->dec = dec; s->mp3 = mp3; s->size = size;
    }
    LeaveCriticalSection(&g_cs);
    return dec;
}

static void jump(Stream *s) {
    int f0 = s->loop->P / FRAME - WARMUP;
    if (f0 < 0) f0 = 0;
    ORIG_SEEK(s->dec, frame_offset(s->mp3, s->size, f0));
    s->discard = s->loop->P - f0 * FRAME;
    s->pos = s->loop->P;
    s->ramp = DECLICK;                             /* the two ends never meet exactly: de-click */
    STAT_JUMPS++;
}

__declspec(dllexport) int __stdcall bof4_decode(void *dec, short *out) {
    static short tmp[2 * FRAME * 2];
    Stream *s; int r = 0, guard = 0;
    EnterCriticalSection(&g_cs);
    s = find(dec);
    if (!s || !s->loop) { LeaveCriticalSection(&g_cs); return ORIG_DECODE(dec, out); }
    while (s->fifo_n < FRAME && guard++ < 64) {
        int n, i;
        r = ORIG_DECODE(dec, tmp);
        n = PRODUCED(dec) / 4;
        if (n > 2 * FRAME) n = 2 * FRAME;
        i = 0;
        if (s->discard) { i = s->discard < n ? s->discard : n; s->discard -= i; }
        for (; i < n; i++) {
            int c, v[2];
            if (s->pos >= s->loop->E) { jump(s); break; }
            for (c = 0; c < 2; c++) {
                v[c] = tmp[2 * i + c];
                if (s->ramp == DECLICK) s->delta[c] = s->last[c] - v[c];   /* first sample after a jump */
                if (s->ramp) v[c] += s->delta[c] * s->ramp / DECLICK;         /* fade the step out */
                if (v[c] > 32767) v[c] = 32767; else if (v[c] < -32768) v[c] = -32768;
                s->fifo[2 * s->fifo_n + c] = (short)(s->last[c] = v[c]);
            }
            if (s->ramp) s->ramp--;
            s->fifo_n++; s->pos++;
        }
        if (i == n && r == DEC_EOF) jump(s);       /* recording ended before E: loop anyway */
    }
    if (s->fifo_n >= FRAME) {
        memcpy(out, s->fifo, FRAME * 4);
        if (g_dump != INVALID_HANDLE_VALUE) { DWORD w; WriteFile(g_dump, out, FRAME * 4, &w, 0); }
        s->fifo_n -= FRAME;
        memmove(s->fifo, s->fifo + 2 * FRAME, s->fifo_n * 4);
        PRODUCED(dec) = FRAME * 4;
        r = 0;
    }
    LeaveCriticalSection(&g_cs);
    return r;
}

void loops_init(int on, const char *ini) {
    InitializeCriticalSection(&g_cs); g_loops_on = on;
    if (GetPrivateProfileIntA("reverb", "dump", 0, ini))
        g_dump = CreateFileA("bof4_loopdump.raw", GENERIC_WRITE, FILE_SHARE_READ, 0, CREATE_ALWAYS, 0, 0);
}
