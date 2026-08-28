#include <stddef.h>

void copy_rows_fixed(int dst[8], const int *src, int rows) {
    /* clamped to the destination and the bound is exclusive */
    if (rows > 8) rows = 8;
    for (int i = 0; i < rows; i++) dst[i] = src[i];
}
