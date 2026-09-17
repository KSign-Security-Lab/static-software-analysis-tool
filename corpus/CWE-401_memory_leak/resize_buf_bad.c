#include <stdlib.h>

char *resize_buf_bad(char *buf, size_t n) {
    buf = realloc(buf, n);
    if (buf == NULL) return NULL;
    return buf;
}
