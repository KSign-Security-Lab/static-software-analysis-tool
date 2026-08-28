#include <stddef.h>

void shrink_len_fixed(const char *src, size_t len) {
    if (len > 32767) return;
    copy_out(src, (short)len);
}
