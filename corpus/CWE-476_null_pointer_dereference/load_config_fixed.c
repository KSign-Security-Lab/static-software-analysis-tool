#include <stdio.h>

void load_config_fixed(const char *path) {
    FILE *f = fopen(path, "r");
    if (f == NULL) return;
    char line[128];
    if (fgets(line, sizeof(line), f) != NULL) apply(line);
    fclose(f);
}
