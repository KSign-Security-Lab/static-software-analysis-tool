/*
 * The vulnerable half of the pair. Compare with download_guarded.c, which has
 * the same shape and is safe.
 *
 * Ground truth:
 *   fetch_firmware   VULNERABLE  CWE-78   url is interpolated into a shell
 *                                         command with no validation
 *   handle_download  VULNERABLE  CWE-78   passes an attacker-controlled field
 *                                         straight through to the sink
 *
 * The chain crosses three functions and two files:
 *   handle_download -> read_param (util.c)   attacker data in
 *   handle_download -> fetch_firmware        no check between
 *   fetch_firmware  -> system                the sink
 *
 * Nothing here can be judged from fetch_firmware alone: whether its argument is
 * attacker controlled is decided in its caller. That is what the callee-first
 * ordering and the note passing are for.
 */
#include "config.h"

#include <stdio.h>
#include <stdlib.h>

void fetch_firmware(const char *url)
{
    char cmd[256];
    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
    system(cmd);
}

void handle_download(const Request *req)
{
    char *target = read_param(req);
    if (target == NULL) {
        return;
    }
    log_line(target);
    fetch_firmware(target);
}
