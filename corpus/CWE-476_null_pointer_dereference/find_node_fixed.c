#include <stddef.h>

int find_node_fixed(struct node *head, int key) {
    for (struct node *n = head; n != NULL; n = n->next)
        if (n->key == key) return n->value;
    return -1;
}
