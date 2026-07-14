/*
 * Synthetic OCPP `UpdateFirmware` example used to exercise the F2-A pipeline.
 *
 * Mirrors the walkthrough in docs/v2/f2a_deck_v7_implementation.html (slide 04):
 *   source : req->location   (external OCPP payload field, untrusted)
 *   flow   : location -> firmware_url -> url -> cmd
 *   sink   : system(cmd)     (COMMAND_EXECUTION)
 *   check  : if (firmware_url == NULL)  -- NULL check only (WEAK)
 *
 * Everything is kept in one translation unit so Joern resolves the
 * dispatch -> handler -> download call graph within a single CPG export.
 */
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

typedef struct Request {
    char *location;
} Request;

void download_firmware(const char *url) {
    char cmd[256];
    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);  /* url -> cmd */
    system(cmd);                                   /* sink */
}

void handle_update_firmware(Request *req) {
    char *firmware_url = req->location;            /* source binding */
    if (firmware_url == NULL) return;              /* check (null only) */
    download_firmware(firmware_url);
}

void dispatch(const char *action, Request *req) {
    if (strcmp(action, "UpdateFirmware") == 0)     /* action string */
        handle_update_firmware(req);               /* handler call */
}
