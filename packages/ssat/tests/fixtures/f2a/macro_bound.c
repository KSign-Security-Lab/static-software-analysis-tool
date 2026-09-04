#include <string.h>

#define MAX_PAYLOAD 256

static unsigned char g_payload[MAX_PAYLOAD];

/* The upper bound is a macro. Joern does not preprocess, so the comparison's
   right-hand side arrives as a pseudo-call rather than a literal -- this is the
   case where the guard reads as unbounded unless the macro is folded. */
int store_payload(const unsigned char *payload, unsigned int length) {
    if (length < MAX_PAYLOAD) {
        memcpy(g_payload, payload, length);
        return 0;
    }
    return -1;
}
