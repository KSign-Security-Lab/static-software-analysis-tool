#include <stdio.h>

void format_row_fixed(const char *user, int id) {
    char row[32];
    snprintf(row, sizeof(row), "user=%s id=%d", user, id);
    emit(row);
}
