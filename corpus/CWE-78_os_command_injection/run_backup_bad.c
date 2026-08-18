#include <stdlib.h>
#include <stdio.h>

void run_backup_bad(const char *dir) {
    /* the directory comes from the request and is pasted into a shell line */
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "tar czf backup.tgz %s", dir);
    system(cmd);
}
