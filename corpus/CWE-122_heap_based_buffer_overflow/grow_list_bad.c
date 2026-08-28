#include <stdlib.h>
#include <string.h>

void grow_list_bad(char **items, int count) {
    /* the new size counts entries, not bytes */
    char **bigger = realloc(items, count + 1);
    bigger[count] = NULL;
    keep(bigger);
}
