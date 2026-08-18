#include <stdio.h>

void read_line_bad(void) {
    /* gets cannot be used safely: it has no length argument at all */
    char line[64];
    gets(line);
    handle(line);
}
