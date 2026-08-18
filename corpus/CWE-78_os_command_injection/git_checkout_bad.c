#include <stdlib.h>
#include <stdio.h>

void git_checkout_bad(const char *ref) {
    /* a branch name is user data and may hold command separators */
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "git checkout %s", ref);
    system(cmd);
}
