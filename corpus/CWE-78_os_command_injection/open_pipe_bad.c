#include <stdio.h>

char *open_pipe_bad(const char *name) {
    char line[128];
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "grep %s /etc/passwd", name);
    FILE *p = popen(cmd, "r");
    return fgets(line, sizeof(line), p);
}
