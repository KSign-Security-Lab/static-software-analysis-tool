#include <stdlib.h>

void drop_twice_bad(char *buf, int failed) {
    /* the error path frees a pointer the caller frees again */
    if (failed) free(buf);
    free(buf);
}
