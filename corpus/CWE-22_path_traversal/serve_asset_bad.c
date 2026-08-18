#include <stdio.h>
#include <stdlib.h>

FILE *serve_asset_bad(const char *rel) {
    /* prefixing a root does not confine anything on its own */
    char path[512];
    snprintf(path, sizeof(path), "/srv/www/%s", rel);
    return fopen(path, "rb");
}
