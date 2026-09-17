#include <stdio.h>

void read_line_fixed(void) {
    char line[64];
    if (fgets(line, sizeof(line), stdin) == NULL) return;
    handle(line);
}
