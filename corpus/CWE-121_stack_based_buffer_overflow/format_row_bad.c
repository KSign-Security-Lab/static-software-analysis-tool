#include <stdio.h>

void format_row_bad(const char *user, int id) {
    char row[32];
    sprintf(row, "user=%s id=%d", user, id);
    emit(row);
}
