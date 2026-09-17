#include <string.h>

void advance_ptr_bad(char *buf, size_t cap, size_t offset, const char *in) {
    memcpy(buf + offset, in, strlen(in));
    (void)cap;
}
