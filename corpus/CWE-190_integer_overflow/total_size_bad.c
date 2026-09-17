#include <stdlib.h>

void *total_size_bad(unsigned header, unsigned body) {
    unsigned total = header + body;
    return malloc(total);
}
