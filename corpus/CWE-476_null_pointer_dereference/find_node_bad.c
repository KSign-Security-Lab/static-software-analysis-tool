#include <stddef.h>

int find_node_bad(struct node *head, int key) {
    struct node *n = head;
    while (n->key != key) n = n->next;
    return n->value;
}
