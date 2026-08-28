#include <stdio.h>

void write_report_bad(FILE *out, const char *line) {
    /* same flaw with an explicit stream */
    fprintf(out, line);
}
