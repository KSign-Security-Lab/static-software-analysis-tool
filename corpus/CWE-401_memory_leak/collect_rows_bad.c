#include <stdlib.h>

void collect_rows_bad(int rows) {
    /* every iteration allocates and only the last one is reachable */
    char *buf = NULL;
    for (int i = 0; i < rows; i++) buf = malloc(64);
    free(buf);
}
