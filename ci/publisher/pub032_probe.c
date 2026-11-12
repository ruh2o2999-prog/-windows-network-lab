#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

/* PUB-032: public synthetic probe only. NO proprietary publisher code. */
int main(int argc, char **argv) {
    static const char payload[] = "PUB032_WINDOWS_NATIVE_PE_EXECUTED\n";
    DWORD wrote = 0;
    HANDLE file;
    if (argc != 2) {
        fputs("usage: pub032_probe.exe OUTFILE\n", stderr);
        return 2;
    }
    file = CreateFileA(argv[1], GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 3;
    if (!WriteFile(file, payload, (DWORD)(sizeof(payload) - 1), &wrote, NULL)
        || wrote != sizeof(payload) - 1) {
        CloseHandle(file);
        return 4;
    }
    if (!FlushFileBuffers(file)) {
        CloseHandle(file);
        return 5;
    }
    if (!CloseHandle(file)) return 6;
    puts("PUB032_WINDOWS_NATIVE_PE_EXECUTED");
    return 0;
}
