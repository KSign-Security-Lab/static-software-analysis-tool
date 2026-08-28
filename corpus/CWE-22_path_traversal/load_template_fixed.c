#include <stdio.h>
#include <string.h>

FILE *load_template_fixed(const char *name) {
    /* the name is checked for shape as well as for suffix */
    size_t n = strlen(name);
    if (n < 5 || strcmp(name + n - 4, ".tpl") != 0) return NULL;
    if (strchr(name, '/') != NULL || strstr(name, "..") != NULL) return NULL;
    char path[256];
    snprintf(path, sizeof(path), "templates/%s", name);
    return fopen(path, "r");
}
