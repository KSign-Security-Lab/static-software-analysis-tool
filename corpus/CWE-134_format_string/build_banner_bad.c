#include <stdio.h>

void build_banner_bad(char *out, size_t cap, const char *name) {
    /* the caller chose the format string and the caller is remote */
    snprintf(out, cap, name);
}
