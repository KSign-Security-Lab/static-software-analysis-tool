#include <stddef.h>

void walk_back_bad(char *buf, size_t len) {
    size_t i = len - 1;
    while (buf[i] == ' ') { buf[i] = 0; i--; }
}
