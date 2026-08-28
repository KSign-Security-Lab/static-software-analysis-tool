#include <stdlib.h>
#include <string.h>

char *take_copy_fixed(const char *in) {
    /* the allocation is checked before it is used */
    char *out = malloc(strlen(in) + 1);
    if (out == NULL) return NULL;
    strcpy(out, in);
    return out;
}
