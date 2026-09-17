#include <stdlib.h>
#include <stdio.h>

void git_checkout_bad(const char *ref) {
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "git checkout %s", ref);
    system(cmd);
}
