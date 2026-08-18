#include <stdlib.h>
#include <string.h>

char *take_copy_bad(const char *in) {
    /* malloc can fail and the result is written to regardless */
    char *out = malloc(strlen(in) + 1);
    strcpy(out, in);
    return out;
}
