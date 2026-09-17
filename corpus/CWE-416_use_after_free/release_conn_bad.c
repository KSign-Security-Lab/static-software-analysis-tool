#include <stdlib.h>

void release_conn_bad(struct conn *c) {
    free(c->name);
    free(c);
    if (c->name != NULL) note("named");
}
