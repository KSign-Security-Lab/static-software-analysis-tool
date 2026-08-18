#include <stdio.h>

FILE *open_upload_fixed(const char *name) {
    /* a bare filename only: no separators, no parent references */
    if (strchr(name, '/') != NULL || strstr(name, "..") != NULL) return NULL;
    char path[256];
    snprintf(path, sizeof(path), "/var/uploads/%s", name);
    return fopen(path, "r");
}
