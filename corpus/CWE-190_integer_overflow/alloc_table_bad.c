#include <stdlib.h>

void *alloc_table_bad(unsigned count, unsigned size) {
    /* the product wraps and a huge request becomes a tiny allocation */
    return malloc(count * size);
}
