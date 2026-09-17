#include <string.h>

void join_parts_fixed(const char *a, const char *b) {
    char out[32];
    if (snprintf(out, sizeof(out), "%s/%s", a, b) >= (int)sizeof(out)) return;
    emit(out);
}
