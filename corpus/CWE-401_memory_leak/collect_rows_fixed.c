#include <stdlib.h>

void collect_rows_fixed(int rows) {
    for (int i = 0; i < rows; i++) {
        char *buf = malloc(64);
        if (buf == NULL) return;
        use_row(buf);
        free(buf);
    }
}
