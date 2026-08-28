#include <stdlib.h>
#include <stdio.h>

void git_checkout_fixed(const char *ref) {
    /* -- ends option parsing and exec takes the ref as one argument */
    if (strchr(ref, '\n') != NULL) return;
    char *argv[] = {"git", "checkout", "--", (char *)ref, NULL};
    posix_spawnp(NULL, "git", NULL, NULL, argv, NULL);
}
