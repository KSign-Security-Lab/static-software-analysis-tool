#include <stdlib.h>
#include <stdio.h>

void apply_env_fixed(void) {
    /* missing or hostile values are refused rather than interpolated */
    const char *upload = getenv("UPLOAD");
    if (upload == NULL || strspn(upload, "abcdefghijklmnopqrstuvwxyz0123456789._-") != strlen(upload)) return;
    char *argv[] = {"convert", (char *)upload, "out.png", NULL};
    posix_spawn(NULL, "/usr/bin/convert", NULL, NULL, argv, NULL);
}
