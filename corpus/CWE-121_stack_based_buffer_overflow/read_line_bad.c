#include <stdio.h>

void read_line_bad(void) {
    char line[64];
    gets(line);
    handle(line);
}
