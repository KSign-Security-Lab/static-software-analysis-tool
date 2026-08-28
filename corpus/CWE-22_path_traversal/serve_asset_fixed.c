#include <stdio.h>
#include <stdlib.h>

FILE *serve_asset_fixed(const char *rel) {
    /* resolved, then proved to still be under the root */
    char path[512];
    snprintf(path, sizeof(path), "/srv/www/%s", rel);
    char *real = realpath(path, NULL);
    if (real == NULL) return NULL;
    FILE *f = strncmp(real, "/srv/www/", 9) == 0 ? fopen(real, "rb") : NULL;
    free(real);
    return f;
}
