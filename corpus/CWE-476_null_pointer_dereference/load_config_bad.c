#include <stdio.h>

void load_config_bad(const char *path) {
    FILE *f = fopen(path, "r");
    char line[128];
    fgets(line, sizeof(line), f);
    fclose(f);
}
