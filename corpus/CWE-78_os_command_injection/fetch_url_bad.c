#include <stdlib.h>
#include <stdio.h>

void fetch_url_bad(const char *url) {
    char cmd[512];
    sprintf(cmd, "wget -O /tmp/f %s", url);
    system(cmd);
}
