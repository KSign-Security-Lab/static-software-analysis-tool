#include <string.h>

void advance_ptr_fixed(char *buf, size_t cap, size_t offset, const char *in) {
    size_t n = strlen(in);
    if (offset > cap || n > cap - offset) return;
    memcpy(buf + offset, in, n);
}
