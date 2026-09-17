#include <stdlib.h>

void release_conn_fixed(struct conn *c) {
    int named = c->name != NULL;
    free(c->name);
    free(c);
    if (named) note("named");
}
