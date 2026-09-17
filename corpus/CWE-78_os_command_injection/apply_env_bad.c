#include <stdlib.h>
#include <stdio.h>

void apply_env_bad(void) {
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "/usr/bin/convert %s out.png", getenv("UPLOAD"));
    system(cmd);
}
