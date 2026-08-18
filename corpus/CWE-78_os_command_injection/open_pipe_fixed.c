#include <stdio.h>

char *open_pipe_fixed(const char *name) {
    /* the needle is passed as an argument, never as shell text */
    static char line[128];
    int fd[2];
    pipe(fd);
    if (fork() == 0) {
        dup2(fd[1], 1);
        execlp("grep", "grep", "--", name, "/etc/passwd", (char *)NULL);
        _exit(127);
    }
    close(fd[1]);
    FILE *p = fdopen(fd[0], "r");
    return fgets(line, sizeof(line), p);
}
