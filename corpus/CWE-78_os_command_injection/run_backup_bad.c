#include <stdlib.h>
#include <stdio.h>

void run_backup_bad(const char *dir) {
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "tar czf backup.tgz %s", dir);
    system(cmd);
}
