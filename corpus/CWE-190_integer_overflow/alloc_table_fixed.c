#include <stdlib.h>

void *alloc_table_fixed(unsigned count, unsigned size) {
    if (size != 0 && count > (unsigned)-1 / size) return NULL;
    return malloc((size_t)count * size);
}
