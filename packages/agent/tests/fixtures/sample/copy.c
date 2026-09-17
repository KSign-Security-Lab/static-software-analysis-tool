/*
 * A second pair, memory rather than command injection, so a run is not scored
 * on one CWE alone.
 *
 * Ground truth:
 *   store_payload         VULNERABLE  CWE-787  copies body_len bytes into a
 *                                              64-byte buffer with no bound
 *   store_payload_guarded SAFE        rejects anything that does not fit
 *
 * The declared size of the destination is in the buffer declaration, one line
 * above the copy -- the kind of fact that lives in the chunk itself. The size
 * of the source is in Request, which is in config.h, and reaches the model
 * through the file chunk rather than this one.
 */
#include "config.h"

#include <string.h>

#define SLOT 64

static char g_slot[SLOT];

void store_payload(const Request *req)
{
    memcpy(g_slot, req->body, req->body_len);
}

void store_payload_guarded(const Request *req)
{
    if (req->body == NULL || req->body_len > sizeof(g_slot)) {
        return;
    }
    memcpy(g_slot, req->body, req->body_len);
}
