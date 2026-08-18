#include <stdio.h>

FILE *read_profile_bad(const char *user) {
    /* an absolute path in user replaces the intended directory entirely */
    char path[256];
    snprintf(path, sizeof(path), "/home/%s/.profile", user);
    return fopen(path, "r");
}
