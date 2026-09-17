#include <stdio.h>

FILE *read_profile_fixed(const char *user) {
    if (user[0] == '/' || strchr(user, '/') != NULL) return NULL;
    char path[256];
    snprintf(path, sizeof(path), "/home/%s/.profile", user);
    return fopen(path, "r");
}
