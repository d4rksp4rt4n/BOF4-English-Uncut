// loopcap <seconds> <out.wav> : record what Windows plays (WASAPI loopback of the default output device)
// to a WAV file in the device's mix format; prints how many capture packets reported a discontinuity.
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <stdio.h>
#include <stdlib.h>
#pragma comment(lib, "ole32.lib")

int main(int argc, char **argv) {
    if (argc < 3) { printf("usage: loopcap seconds out.wav\n"); return 1; }
    int secs = atoi(argv[1]);
    FILE *f = fopen(argv[2], "wb");
    CoInitialize(0);
    IMMDeviceEnumerator *en; IMMDevice *dev; IAudioClient *ac; IAudioCaptureClient *cc; WAVEFORMATEX *wf;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), 0, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), (void **)&en)) ||
        FAILED(en->GetDefaultAudioEndpoint(eRender, eConsole, &dev)) ||
        FAILED(dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, 0, (void **)&ac)) ||
        FAILED(ac->GetMixFormat(&wf)) ||
        FAILED(ac->Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK, 10000000, 0, wf, 0)) ||
        FAILED(ac->GetService(__uuidof(IAudioCaptureClient), (void **)&cc))) { printf("WASAPI setup failed\n"); return 1; }
    DWORD fmtlen = sizeof(WAVEFORMATEX) + wf->cbSize, data = 0, riff = 0;
    fwrite("RIFF\0\0\0\0WAVEfmt ", 1, 16, f); fwrite(&fmtlen, 4, 1, f); fwrite(wf, 1, fmtlen, f);
    fwrite("data\0\0\0\0", 1, 8, f);
    long hdr = ftell(f) - 4;
    printf("recording %d s, %lu Hz, %u ch, %u bits\n", secs, wf->nSamplesPerSec, wf->nChannels, wf->wBitsPerSample);
    ac->Start();
    DWORD t0 = GetTickCount(); int disc = 0;
    static BYTE zero[1 << 16];
    while (GetTickCount() - t0 < (DWORD)secs * 1000) {
        Sleep(5);
        UINT32 n;
        while (SUCCEEDED(cc->GetNextPacketSize(&n)) && n) {
            BYTE *p; UINT32 frames; DWORD flags;
            if (FAILED(cc->GetBuffer(&p, &frames, &flags, 0, 0))) break;
            DWORD bytes = frames * wf->nBlockAlign;
            if (flags & AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY) disc++;
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) { for (DWORD k = 0; k < bytes; k += sizeof zero) fwrite(zero, 1, min((DWORD)sizeof zero, bytes - k), f); }
            else fwrite(p, 1, bytes, f);
            data += bytes;
            cc->ReleaseBuffer(frames);
        }
    }
    ac->Stop();
    riff = data + hdr - 4;
    fseek(f, 4, SEEK_SET); fwrite(&riff, 4, 1, f); fseek(f, hdr, SEEK_SET); fwrite(&data, 4, 1, f); fclose(f);
    printf("done: %.1f s recorded, %d discontinuities reported by Windows\n", data / (double)wf->nAvgBytesPerSec, disc);
    return 0;
}
