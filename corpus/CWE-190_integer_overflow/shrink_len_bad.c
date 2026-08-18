#include <stddef.h>

void shrink_len_bad(const char *src, size_t len) {
    /* the length is truncated into a short before it is used */
    short n = (short)len;
    copy_out(src, n);
}
