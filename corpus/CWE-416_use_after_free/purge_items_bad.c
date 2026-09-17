#include <stdlib.h>

void purge_items_bad(struct item *head) {
    for (struct item *it = head; it != NULL; it = it->next) free(it);
}
