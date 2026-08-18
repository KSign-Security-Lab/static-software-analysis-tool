#include <stdlib.h>
#include <string.h>

char *append_tag_fixed(const char *base, const char *tag) {
    /* sized for both halves and the terminator */
    size_t n = strlen(base) + strlen(tag) + 1;
    char *out = malloc(n);
    if (out == NULL) return NULL;
    snprintf(out, n, "%s%s", base, tag);
    return out;
}
