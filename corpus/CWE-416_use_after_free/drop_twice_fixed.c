#include <stdlib.h>

void drop_twice_fixed(char *buf, int failed) {
    (void)failed;
    free(buf);
}
