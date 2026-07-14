/*
 * Variant of update_firmware.c that DOES perform scheme + signature checks.
 * Used to prove the F2-A check classifier is genuinely structural (symbol +
 * operand based), detecting checks without any regex over source text:
 *   - if (strncmp(firmware_url, "https://", 8) != 0)  -> URL_SCHEME_CHECK (STRONG)
 *   - if (!verify_signature(firmware_url))            -> SIGNATURE_VERIFICATION (STRONG)
 *   - if (firmware_url == NULL)                       -> NULL_CHECK (WEAK)
 * The sink is still system(cmd), so SAFE_DOWNLOAD_API_NO_SHELL stays NEGATIVE.
 */
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

typedef struct Request {
    char *location;
} Request;

int verify_signature(const char *path);

void download_firmware(const char *url) {
    char cmd[256];
    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
    system(cmd);
}

void handle_update_firmware(Request *req) {
    char *firmware_url = req->location;
    if (firmware_url == NULL) return;
    if (strncmp(firmware_url, "https://", 8) != 0) return;  /* URL scheme check */
    if (!verify_signature(firmware_url)) return;            /* signature check */
    download_firmware(firmware_url);
}

void dispatch(const char *action, Request *req) {
    if (strcmp(action, "UpdateFirmware") == 0)
        handle_update_firmware(req);
}
