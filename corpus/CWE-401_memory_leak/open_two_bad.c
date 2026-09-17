#include <stdlib.h>

int open_two_bad(int n) {
    char *a = malloc((size_t)n);
    char *b = malloc((size_t)n);
    if (b == NULL) return -1;
    free(a);
    free(b);
    return 0;
}
