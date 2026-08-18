#include <stdio.h>

void format_row_bad(const char *user, int id) {
    /* sprintf has no idea how big row is */
    char row[32];
    sprintf(row, "user=%s id=%d", user, id);
    emit(row);
}
