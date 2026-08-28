#include <stdlib.h>

char *extend_buf_bad(char *buf, size_t n) {
    /* realloc may move the block, leaving the old pointer dangling */
    realloc(buf, n);
    buf[0] = 0;
    return buf;
}
