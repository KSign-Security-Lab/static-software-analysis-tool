#include <stdlib.h>

void collect_rows_bad(int rows) {
    char *buf = NULL;
    for (int i = 0; i < rows; i++) buf = malloc(64);
    free(buf);
}
