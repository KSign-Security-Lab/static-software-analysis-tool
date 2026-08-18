#include <stddef.h>

int find_node_bad(struct node *head, int key) {
    /* the loop dereferences before testing for the end of the list */
    struct node *n = head;
    while (n->key != key) n = n->next;
    return n->value;
}
