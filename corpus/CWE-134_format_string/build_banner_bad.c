#include <stdio.h>

void build_banner_bad(char *out, size_t cap, const char *name) {
    snprintf(out, cap, name);
}
