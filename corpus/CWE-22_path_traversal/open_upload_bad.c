#include <stdio.h>

FILE *open_upload_bad(const char *name) {
    /* ../ in name walks straight out of the upload directory */
    char path[256];
    snprintf(path, sizeof(path), "/var/uploads/%s", name);
    return fopen(path, "r");
}
