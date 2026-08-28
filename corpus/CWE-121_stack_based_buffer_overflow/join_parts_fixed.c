#include <string.h>

void join_parts_fixed(const char *a, const char *b) {
    /* one bounded write that cannot exceed the buffer */
    char out[32];
    if (snprintf(out, sizeof(out), "%s/%s", a, b) >= (int)sizeof(out)) return;
    emit(out);
}
