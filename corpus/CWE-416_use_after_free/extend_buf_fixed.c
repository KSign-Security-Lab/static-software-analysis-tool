#include <stdlib.h>

char *extend_buf_fixed(char *buf, size_t n) {
    char *moved = realloc(buf, n);
    if (moved == NULL) return buf;
    moved[0] = 0;
    return moved;
}
