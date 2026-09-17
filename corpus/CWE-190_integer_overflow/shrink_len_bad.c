#include <stddef.h>

void shrink_len_bad(const char *src, size_t len) {
    short n = (short)len;
    copy_out(src, n);
}
