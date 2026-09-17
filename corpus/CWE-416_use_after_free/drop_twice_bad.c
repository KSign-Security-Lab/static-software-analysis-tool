#include <stdlib.h>

void drop_twice_bad(char *buf, int failed) {
    if (failed) free(buf);
    free(buf);
}
