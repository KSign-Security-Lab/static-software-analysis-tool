#include <stdlib.h>
#include <string.h>

void grow_list_fixed(char **items, int count) {
    /* bytes, and the original pointer is not lost if realloc fails */
    char **bigger = realloc(items, (size_t)(count + 1) * sizeof(*items));
    if (bigger == NULL) return;
    bigger[count] = NULL;
    keep(bigger);
}
