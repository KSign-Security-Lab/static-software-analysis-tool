#include <stdlib.h>

void drop_twice_fixed(char *buf, int failed) {
    /* one owner, one free */
    (void)failed;
    free(buf);
}
