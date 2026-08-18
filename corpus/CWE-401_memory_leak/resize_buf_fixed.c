#include <stdlib.h>

char *resize_buf_fixed(char *buf, size_t n) {
    char *moved = realloc(buf, n);
    if (moved == NULL) { free(buf); return NULL; }
    return moved;
}
