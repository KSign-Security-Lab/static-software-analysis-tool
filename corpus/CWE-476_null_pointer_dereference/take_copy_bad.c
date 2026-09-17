#include <stdlib.h>
#include <string.h>

char *take_copy_bad(const char *in) {
    char *out = malloc(strlen(in) + 1);
    strcpy(out, in);
    return out;
}
