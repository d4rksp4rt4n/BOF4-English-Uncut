/* BOF4 PC: PlayStation SPU reverb for the music.
 *
 * The PC port plays its music as MP3 streams with no reverb; the PS1 runs every song through the SPU
 * reverb ("Studio Medium", depth 0x40 of 0x7F: the sound driver's per-bank type table at 0x80174400
 * holds 3 for all four banks, and SsUtSetReverbDepth(0x40, 0x40)).
 * BOF4.exe (patched by build_mod.py) calls bof4_reverb_block(stream, flags) after every 0x12000-byte
 * block it decodes into 0xABC6AC (44.1 kHz stereo s16): flags bit 1 = first block of a new stream,
 * bit 0 = the stream was started by the music player.
 *
 * The algorithm is the SPU's (see psx-spx, "SPU Reverb Formula"): 44.1 kHz input decimated through
 * a windowed-sinc filter (see FIR below), reverb at 22.05 kHz on a 16-bit work buffer, interpolated back with
 * the same FIR. Optional BOF4_reverb.ini next to the exe: [reverb] wet=100 (% of the PS1 level), sfx=0.
 */
#include <windows.h>
#include <string.h>
#include <math.h>

#define PCM ((short *)0x00ABC6AC)
#define PCM_FRAMES (0x12000 / 4)
#define MAX_STREAMS 16
#define RING 0x10000                      /* > largest offset used by any preset (in 16-bit words) */

/* Studio Medium, from the PS1 executable's libspu table (0x80174FEC + 3 * 0x44 + 4) */
static const unsigned short PRESET[32] = {
    0x00B1, 0x007F, 0x70F0, 0x4FA8, 0xBCE0, 0x4510, 0xBEF0, 0xB4C0, 0x5280, 0x4EC0, 0x0904, 0x076B,
    0x0824, 0x065F, 0x07A2, 0x0616, 0x076C, 0x05ED, 0x05EC, 0x042E, 0x050F, 0x0305, 0x0462, 0x02B7,
    0x042F, 0x0265, 0x0264, 0x01B2, 0x0100, 0x0080, 0x8000, 0x8000};
enum { dAPF1, dAPF2, vIIR, vCOMB1, vCOMB2, vCOMB3, vCOMB4, vWALL, vAPF1, vAPF2, mLSAME, mRSAME,
       mLCOMB1, mRCOMB1, mLCOMB2, mRCOMB2, dLSAME, dRSAME, mLDIFF, mRDIFF, mLCOMB3, mRCOMB3,
       mLCOMB4, mRCOMB4, dLDIFF, dRDIFF, mLAPF1, mRAPF1, mLAPF2, mRAPF2, vLIN, vRIN };
#define DEPTH (0x40 / 127.0f)               /* SsUtSetReverbDepth(0x40, 0x40) */
#define HEADROOM 4.f

/* 44.1 <-> 22.05 kHz resampling filter. The SPU's own 39-tap half-band filter leaves the upsampling
   images of the reverb (mirrored to 16-22 kHz) only weakly damped; on a PS1 the analog output stage
   hides them, but added to the PC's MP3s (which stop at ~16 kHz) they are a clearly audible whine.
   So: a 95-tap Blackman-windowed sinc, cutoff 10 kHz, built in DllMain. */
#define TAPS 95
static float FIR[TAPS];

typedef struct {
    short buf[RING];
    unsigned pos;
    float in_l[TAPS], in_r[TAPS], out_l[TAPS], out_r[TAPS];   /* histories, newest at index 0 */
    int phase, music;
    float atten;                                  /* limiter gain reduction, 0 = none */
} State;

static State *st[MAX_STREAMS];
void loops_init(int on, const char *ini);         /* loops.c */
static float g_v[32], g_wet = 1.0f;
static int g_off[32], g_sfx = 0;

static long g_sat;
static float sat(float v) { if (v > 32767.f || v < -32768.f) { g_sat++; return v > 0 ? 32767.f : -32768.f; } return v; }
static float rd(State *s, int off) { return s->buf[(s->pos + off) & (RING - 1)]; }
static void wr(State *s, int off, float v) { s->buf[(s->pos + off) & (RING - 1)] = (short)sat(v); }
static void push(float *h, float v) { memmove(h + 1, h, (TAPS - 1) * sizeof(float)); h[0] = v; }
static float fir(const float *h) {
    float a = 0; int i;
    for (i = 0; i < TAPS; i++) a += h[i] * FIR[i];
    return a;
}
static void make_fir(void) {                      /* unity DC gain; cutoff 10 kHz at 44.1 kHz */
    const double fc = 10000.0 / 44100.0, PI = 3.14159265358979; double sum = 0; int i;
    for (i = 0; i < TAPS; i++) {
        double x = i - (TAPS - 1) / 2.0, w = 0.42 - 0.5 * cos(2 * PI * i / (TAPS - 1)) + 0.08 * cos(4 * PI * i / (TAPS - 1));
        FIR[i] = (float)((x == 0 ? 2 * fc : sin(2 * PI * fc * x) / (PI * x)) * w); sum += FIR[i];
    }
    for (i = 0; i < TAPS; i++) FIR[i] = (float)(FIR[i] / sum);
}

static void tick(State *s, float L, float R, float *ol, float *or_) {
    const int *o = g_off; const float *v = g_v; float Lin = v[vLIN] * L, Rin = v[vRIN] * R, Lo, Ro;
    wr(s, o[mLSAME], (Lin + rd(s, o[dLSAME]) * v[vWALL] - rd(s, o[mLSAME] - 1)) * v[vIIR] + rd(s, o[mLSAME] - 1));
    wr(s, o[mRSAME], (Rin + rd(s, o[dRSAME]) * v[vWALL] - rd(s, o[mRSAME] - 1)) * v[vIIR] + rd(s, o[mRSAME] - 1));
    wr(s, o[mLDIFF], (Lin + rd(s, o[dRDIFF]) * v[vWALL] - rd(s, o[mLDIFF] - 1)) * v[vIIR] + rd(s, o[mLDIFF] - 1));
    wr(s, o[mRDIFF], (Rin + rd(s, o[dLDIFF]) * v[vWALL] - rd(s, o[mRDIFF] - 1)) * v[vIIR] + rd(s, o[mRDIFF] - 1));
    Lo = v[vCOMB1] * rd(s, o[mLCOMB1]) + v[vCOMB2] * rd(s, o[mLCOMB2]) + v[vCOMB3] * rd(s, o[mLCOMB3]) + v[vCOMB4] * rd(s, o[mLCOMB4]);
    Ro = v[vCOMB1] * rd(s, o[mRCOMB1]) + v[vCOMB2] * rd(s, o[mRCOMB2]) + v[vCOMB3] * rd(s, o[mRCOMB3]) + v[vCOMB4] * rd(s, o[mRCOMB4]);
    Lo = sat(Lo - v[vAPF1] * rd(s, o[mLAPF1] - o[dAPF1])); wr(s, o[mLAPF1], Lo); Lo = Lo * v[vAPF1] + rd(s, o[mLAPF1] - o[dAPF1]);
    Ro = sat(Ro - v[vAPF1] * rd(s, o[mRAPF1] - o[dAPF1])); wr(s, o[mRAPF1], Ro); Ro = Ro * v[vAPF1] + rd(s, o[mRAPF1] - o[dAPF1]);
    Lo = sat(Lo - v[vAPF2] * rd(s, o[mLAPF2] - o[dAPF2])); wr(s, o[mLAPF2], Lo); Lo = Lo * v[vAPF2] + rd(s, o[mLAPF2] - o[dAPF2]);
    Ro = sat(Ro - v[vAPF2] * rd(s, o[mRAPF2] - o[dAPF2])); wr(s, o[mRAPF2], Ro); Ro = Ro * v[vAPF2] + rd(s, o[mRAPF2] - o[dAPF2]);
    s->pos++;
    *ol = sat(Lo) * DEPTH; *or_ = sat(Ro) * DEPTH;
}

/* Some PC tracks are mastered right up to full scale, so dry + reverb can exceed it. A peak limiter
   (instant attack, ~150 ms release) turns the level down briefly instead of distorting the waveform;
   anything below LIMIT passes through untouched. */
#define LIMIT 32700.f
#define RELEASE (1.f / (0.15f * 44100.f))

static void process(State *s, short *pcm, int frames) {
    int n;
    for (n = 0; n < frames; n++) {
        float l = pcm[2 * n], r = pcm[2 * n + 1], wl = 0, wr_ = 0, yl, yr, pk, g;
        push(s->in_l, l); push(s->in_r, r);
        /* 22.05 kHz. HEADROOM: the PC tracks are mastered far hotter than the SPU's internal mix and
           would clip the reverb's 16-bit work buffer (a harsh buzz on drums); the reverb is linear, so
           run it at a lower level and scale the result back (wet is multiplied by HEADROOM below). */
        if (s->phase ^= 1) tick(s, fir(s->in_l) / HEADROOM, fir(s->in_r) / HEADROOM, &wl, &wr_);
        push(s->out_l, wl); push(s->out_r, wr_);                               /* zero-stuffed */
        yl = l + 2.f * HEADROOM * fir(s->out_l) * g_wet;
        yr = r + 2.f * HEADROOM * fir(s->out_r) * g_wet;
        pk = fabsf(yl) > fabsf(yr) ? fabsf(yl) : fabsf(yr);
        g = 1.f - s->atten;                                  /* current gain */
        if (pk * g > LIMIT) g = LIMIT / pk;                  /* attack: just enough to fit */
        else g += (1.f - g) * RELEASE;                       /* release toward unity */
        s->atten = 1.f - g;
        pcm[2 * n]     = (short)sat(yl * g);
        pcm[2 * n + 1] = (short)sat(yr * g);
    }
}

/* ini log=1: write music refills that come late (main-thread stalls) to bof4_audio_log.txt */
static HANDLE g_log = INVALID_HANDLE_VALUE;
static LARGE_INTEGER g_freq, g_t0, g_last[MAX_STREAMS];
static void log_refill(int stream, int flags) {
    LARGE_INTEGER now; double gap;
    QueryPerformanceCounter(&now);
    gap = g_last[stream].QuadPart ? (double)(now.QuadPart - g_last[stream].QuadPart) / g_freq.QuadPart : 0;
    g_last[stream] = now;
    if (flags & 2) {                            /* a stream starts */
        char line[96]; DWORD w;
        int n = wsprintfA(line, "%u.%03u s  stream %d  starts (%s)\r\n",
            (unsigned)((now.QuadPart - g_t0.QuadPart) / g_freq.QuadPart),
            (unsigned)((now.QuadPart - g_t0.QuadPart) * 1000 / g_freq.QuadPart % 1000), stream,
            flags & 1 ? "music player" : "other: sound effect or jingle");
        WriteFile(g_log, line, n, &w, 0);
    }
    if (!(flags & 2) && gap > 0.5) {            /* blocks are 0.418 s; this much later risks an underrun */
        char line[96]; DWORD w;
        int n = wsprintfA(line, "%u.%03u s  stream %d  refill %u ms after the previous one%s\r\n",
            (unsigned)((now.QuadPart - g_t0.QuadPart) / g_freq.QuadPart),
            (unsigned)((now.QuadPart - g_t0.QuadPart) * 1000 / g_freq.QuadPart % 1000), stream,
            (unsigned)(gap * 1000), gap > 0.836 ? "  <- music must have skipped" : "");
        WriteFile(g_log, line, n, &w, 0);
    }
}

__declspec(dllexport) void __cdecl bof4_reverb_block(int stream, int flags) {
    State *s;
    if (stream < 0 || stream >= MAX_STREAMS) return;
    if (g_log != INVALID_HANDLE_VALUE) log_refill(stream, flags);
    if (!st[stream] && !(st[stream] = (State *)VirtualAlloc(0, sizeof(State), MEM_COMMIT, PAGE_READWRITE))) return;
    s = st[stream];
    if (flags & 2) { memset(s, 0, sizeof(State)); s->music = flags & 1; }  /* new stream */
    if (g_wet > 0 && (s->music || g_sfx)) process(s, PCM, PCM_FRAMES);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    if (why == DLL_PROCESS_ATTACH) {
        make_fir();
        char ini[MAX_PATH], *p; int i;
        for (i = 0; i < 32; i++) {
            g_v[i] = (short)PRESET[i] / 32768.f;
            g_off[i] = PRESET[i] * 4;               /* registers count 8-byte units; buffer is 16-bit */
        }
        GetModuleFileNameA(0, ini, MAX_PATH);
        if ((p = strrchr(ini, '\\')) != 0) strcpy(p + 1, "BOF4_reverb.ini");
        g_wet = GetPrivateProfileIntA("reverb", "wet", 100, ini) / 100.f;
        g_sfx = GetPrivateProfileIntA("reverb", "sfx", 0, ini);
        if (GetPrivateProfileIntA("reverb", "log", 0, ini)) {
            QueryPerformanceFrequency(&g_freq); QueryPerformanceCounter(&g_t0);
            g_log = CreateFileA("bof4_audio_log.txt", GENERIC_WRITE, FILE_SHARE_READ, 0, CREATE_ALWAYS, 0, 0);
        }
#ifndef REVERB_TEST
        loops_init(*(volatile unsigned char *)0x006A7B01 & 2, ini);   /* exe stub's feature byte: 1 reverb, 2 loops */
#endif
    }
    return TRUE;
}

#ifdef REVERB_TEST   /* reverb_test in.raw out.raw : s16le 44.1 kHz stereo, same processing as in game */
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    FILE *f = fopen(argv[1], "rb"); long n; short *pcm; State *s = (State *)calloc(1, sizeof(State));
    DllMain(0, DLL_PROCESS_ATTACH, 0);
    fseek(f, 0, SEEK_END); n = ftell(f) / 4; fseek(f, 0, SEEK_SET);
    pcm = (short *)malloc(n * 4 + PCM_FRAMES * 4); fread(pcm, 4, n, f); fclose(f);
    memset(pcm + 2 * n, 0, PCM_FRAMES * 4);                  /* let the tail ring out */
    process(s, pcm, n + PCM_FRAMES);
    printf("saturations: %ld over %ld frames\n", g_sat, n);
    f = fopen(argv[2], "wb"); fwrite(pcm, 4, n + PCM_FRAMES, f); fclose(f);
    return 0;
}
#endif
