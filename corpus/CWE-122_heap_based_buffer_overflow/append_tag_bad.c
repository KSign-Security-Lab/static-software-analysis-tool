#include <stdlib.h>
#include <string.h>

char *append_tag_bad(const char *base, const char *tag) {
    /* sized for base alone, then written with base and tag */
    char *out = malloc(strlen(base) + 1);
    strcpy(out, base);
    strcat(out, tag);
    return out;
}
