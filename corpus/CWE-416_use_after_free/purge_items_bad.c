#include <stdlib.h>

void purge_items_bad(struct item *head) {
    /* the link is followed out of memory that has just been released */
    for (struct item *it = head; it != NULL; it = it->next) free(it);
}
