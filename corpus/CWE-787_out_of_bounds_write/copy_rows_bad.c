#include <stddef.h>

void copy_rows_bad(int dst[8], const int *src, int rows) {
    for (int i = 0; i <= rows; i++) dst[i] = src[i];
}
