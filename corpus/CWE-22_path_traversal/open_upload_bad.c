#include <stdio.h>

FILE *open_upload_bad(const char *name) {
    char path[256];
    snprintf(path, sizeof(path), "/var/uploads/%s", name);
    return fopen(path, "r");
}
