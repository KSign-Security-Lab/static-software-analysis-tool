#include <stdlib.h>
#include <stdio.h>

void fetch_url_fixed(const char *url) {
    /* reject anything that is not a plain http(s) URL before it reaches exec */
    if (strncmp(url, "https://", 8) != 0) return;
    if (strpbrk(url, ";|&$`<>\n") != NULL) return;
    char *argv[] = {"wget", "-O", "/tmp/f", (char *)url, NULL};
    posix_spawnp(NULL, "wget", NULL, NULL, argv, NULL);
}
