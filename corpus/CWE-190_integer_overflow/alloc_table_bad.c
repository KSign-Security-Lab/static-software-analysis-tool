#include <stdlib.h>

void *alloc_table_bad(unsigned count, unsigned size) {
    return malloc(count * size);
}
