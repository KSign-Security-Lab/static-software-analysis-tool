#include <stdlib.h>

void *total_size_fixed(unsigned header, unsigned body) {
    if (header > (unsigned)-1 - body) return NULL;
    return malloc((size_t)header + body);
}
