#include <stdlib.h>
#include <string.h>

void grow_list_fixed(char **items, int count) {
    char **bigger = realloc(items, (size_t)(count + 1) * sizeof(*items));
    if (bigger == NULL) return;
    bigger[count] = NULL;
    keep(bigger);
}
