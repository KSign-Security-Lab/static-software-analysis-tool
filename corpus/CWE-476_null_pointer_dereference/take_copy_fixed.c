#include <stdlib.h>
#include <string.h>

char *take_copy_fixed(const char *in) {
    char *out = malloc(strlen(in) + 1);
    if (out == NULL) return NULL;
    strcpy(out, in);
    return out;
}
