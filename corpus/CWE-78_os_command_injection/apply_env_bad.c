#include <stdlib.h>
#include <stdio.h>

void apply_env_bad(void) {
    /* the environment is attacker input in a setuid or CGI context */
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "/usr/bin/convert %s out.png", getenv("UPLOAD"));
    system(cmd);
}
