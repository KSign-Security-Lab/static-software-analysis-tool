#include <stdlib.h>

char *resize_buf_bad(char *buf, size_t n) {
    /* on failure realloc returns NULL and the original is lost */
    buf = realloc(buf, n);
    if (buf == NULL) return NULL;
    return buf;
}
