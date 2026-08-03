/*
 * The safe half of the pair. Same shape as download.c.
 *
 * Ground truth:
 *   fetch_firmware_guarded   SAFE   no shell: execv takes an argument vector,
 *                                   so the url cannot become shell syntax
 *   handle_download_guarded  SAFE   rejects anything that is not https:// and
 *                                   bounds the length before use
 *
 * A finding on either function is a false positive. This file is the reason the
 * pair exists: flagging download.c is easy, and staying quiet here is what
 * separates a useful analyser from one that flags every system() it sees.
 */
#include "config.h"

#include <string.h>
#include <unistd.h>

#define MAX_URL 512

void fetch_firmware_guarded(const char *url)
{
    char *const argv[] = {"/usr/bin/wget", (char *)url, "-O", "/tmp/fw.bin", NULL};
    execv(argv[0], argv);
}

void handle_download_guarded(const Request *req)
{
    char *target = read_param(req);
    if (target == NULL) {
        return;
    }
    if (strncmp(target, "https://", 8) != 0) {
        return;
    }
    if (strnlen(target, MAX_URL + 1) > MAX_URL) {
        return;
    }
    log_line(target);
    fetch_firmware_guarded(target);
}
