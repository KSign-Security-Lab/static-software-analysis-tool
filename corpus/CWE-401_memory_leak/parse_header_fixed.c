#include <stdlib.h>
#include <string.h>

int parse_header_fixed(const char *raw) {
    char *copy = strdup(raw);
    if (copy == NULL) return -1;
    int n = strncmp(copy, "GET ", 4) == 0 ? (int)strlen(copy) : -1;
    free(copy);
    return n;
}
