#include <stdio.h>
#include <string.h>

FILE *load_template_bad(const char *name) {
    if (strstr(name, ".tpl") == NULL) return NULL;
    char path[256];
    snprintf(path, sizeof(path), "templates/%s", name);
    return fopen(path, "r");
}
