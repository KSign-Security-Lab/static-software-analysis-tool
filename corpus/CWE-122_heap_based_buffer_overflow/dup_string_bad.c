#include <stdlib.h>
#include <string.h>

char *dup_string_bad(const char *in) {
    /* strlen does not count the terminator, so this is one byte short */
    char *copy = malloc(strlen(in));
    strcpy(copy, in);
    return copy;
}
