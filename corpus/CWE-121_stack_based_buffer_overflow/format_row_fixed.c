#include <stdio.h>

void format_row_fixed(const char *user, int id) {
    /* snprintf truncates instead of running past the end */
    char row[32];
    snprintf(row, sizeof(row), "user=%s id=%d", user, id);
    emit(row);
}
