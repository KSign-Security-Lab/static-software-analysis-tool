#include <string.h>

void advance_ptr_bad(char *buf, size_t cap, size_t offset, const char *in) {
    /* offset may already be past the end before the copy starts */
    memcpy(buf + offset, in, strlen(in));
    (void)cap;
}
