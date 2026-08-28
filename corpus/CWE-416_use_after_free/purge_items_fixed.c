#include <stdlib.h>

void purge_items_fixed(struct item *head) {
    /* the next pointer is saved before the node goes */
    struct item *it = head;
    while (it != NULL) { struct item *next = it->next; free(it); it = next; }
}
