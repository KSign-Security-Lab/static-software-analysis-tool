#include <stddef.h>

void walk_back_fixed(char *buf, size_t len) {
    /* the empty case is handled before any index is formed */
    size_t i = len;
    while (i > 0 && buf[i - 1] == ' ') { buf[i - 1] = 0; i--; }
}
