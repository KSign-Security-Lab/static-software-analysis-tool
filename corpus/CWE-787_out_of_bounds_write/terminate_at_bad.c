#include <string.h>

void terminate_at_bad(char *buf, size_t cap, const char *in) {
    /* writes the terminator at cap, which is one past the last element */
    size_t n = strlen(in);
    memcpy(buf, in, n < cap ? n : cap);
    buf[cap] = 0;
}
