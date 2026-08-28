#include <stddef.h>

void walk_back_bad(char *buf, size_t len) {
    /* a length of zero makes the index wrap to the end of the range */
    size_t i = len - 1;
    while (buf[i] == ' ') { buf[i] = 0; i--; }
}
