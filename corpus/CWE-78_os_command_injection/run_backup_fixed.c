#include <stdlib.h>
#include <stdio.h>

void run_backup_fixed(const char *dir) {
    /* no shell: the argument stays one argv entry whatever it contains */
    pid_t pid = fork();
    if (pid == 0) {
        execlp("tar", "tar", "czf", "backup.tgz", dir, (char *)NULL);
        _exit(127);
    }
    waitpid(pid, NULL, 0);
}
