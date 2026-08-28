#include <stdio.h>

void write_report_fixed(FILE *out, const char *line) {
    fprintf(out, "%s", line);
}
