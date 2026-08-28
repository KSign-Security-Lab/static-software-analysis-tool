#include <stdio.h>

void build_banner_fixed(char *out, size_t cap, const char *name) {
    snprintf(out, cap, "%s", name);
}
