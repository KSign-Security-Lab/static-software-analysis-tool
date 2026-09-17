#include <string.h>

void join_parts_bad(const char *a, const char *b) {
    char out[32];
    strcpy(out, a);
    strcat(out, "/");
    strcat(out, b);
    emit(out);
}
