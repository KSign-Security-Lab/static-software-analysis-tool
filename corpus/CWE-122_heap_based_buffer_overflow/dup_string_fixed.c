#include <stdlib.h>
#include <string.h>

char *dup_string_fixed(const char *in) {
    size_t n = strlen(in) + 1;
    char *copy = malloc(n);
    if (copy == NULL) return NULL;
    memcpy(copy, in, n);
    return copy;
}
