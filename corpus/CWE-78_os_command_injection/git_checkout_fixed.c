#include <stdlib.h>
#include <stdio.h>

void git_checkout_fixed(const char *ref) {
    if (strchr(ref, '\n') != NULL) return;
    char *argv[] = {"git", "checkout", "--", (char *)ref, NULL};
    posix_spawnp(NULL, "git", NULL, NULL, argv, NULL);
}
