#include <stdio.h>
#include <stdlib.h>

FILE *serve_asset_bad(const char *rel) {
    char path[512];
    snprintf(path, sizeof(path), "/srv/www/%s", rel);
    return fopen(path, "rb");
}
