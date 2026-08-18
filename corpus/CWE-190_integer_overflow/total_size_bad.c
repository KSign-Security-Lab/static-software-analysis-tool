#include <stdlib.h>

void *total_size_bad(unsigned header, unsigned body) {
    /* the sum wraps and under-allocates for the two parts */
    unsigned total = header + body;
    return malloc(total);
}
