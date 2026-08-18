#include <stdio.h>

void read_line_fixed(void) {
    /* fgets stops at the buffer size and keeps the terminator */
    char line[64];
    if (fgets(line, sizeof(line), stdin) == NULL) return;
    handle(line);
}
