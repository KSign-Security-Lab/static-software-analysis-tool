#include <stdlib.h>
#include <string.h>

int parse_header_bad(const char *raw) {
    /* the early return abandons the allocation */
    char *copy = strdup(raw);
    if (strncmp(copy, "GET ", 4) != 0) return -1;
    int n = (int)strlen(copy);
    free(copy);
    return n;
}
