#include <stdlib.h>

int open_two_fixed(int n) {
    char *a = malloc((size_t)n);
    char *b = malloc((size_t)n);
    if (a == NULL || b == NULL) { free(a); free(b); return -1; }
    free(a);
    free(b);
    return 0;
}
