#include <stdlib.h>
#include <string.h>

char *dup_string_bad(const char *in) {
    char *copy = malloc(strlen(in));
    strcpy(copy, in);
    return copy;
}
